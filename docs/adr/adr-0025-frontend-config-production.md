# ADR-0025: Production frontend и session boundary — env-Host/CORS/proxy, cookie-флаги и `/data`

Дата: 2026-09-22
Статус: Accepted
Связанные: [ADR-0020](adr-0020-hosted-web-oauth-and-sessions.md), [ADR-0024](adr-0024-teacher-mode-api-surface.md), [ADR-0016](adr-0016-production-nuitka-packaging.md), [ADR-0019](adr-0019-oauth-flow-owned-by-app.md)
Источник: `docs/migration/Frontend and Configuration Part 1/2 num in query 7.md` (§26–§31, §51), аудит `docs/migration/audits/HOSTING_MIGRATION_AUDIT.md`.

## Контекст

До этапа 7 hosted-фронтенд был адаптирован к серверным сессиям лишь
частично: `DataContext` не различал «нет сессии» и сетевую ошибку, React
не имел единой реакции на `401`, а backend всё ещё использовал
desktop-допущения — `FRONTEND_ORIGINS = localhost:5173`, жёсткий
`TRUSTED_HOSTS = 127.0.0.1/localhost` и CORS с localhost-списком
(аудит C3/S1/S2, F2). Hosted-сервис за Caddy должен:

- отдавать UI и `/api` с **одного публичного origin**, без permissive CORS;
- принимать публичный домен из конфигурации, а localhost — только в
  development (§27/§28);
- понимать внешнюю HTTPS-схему и host за trusted proxy, не доверяя
  произвольным `X-Forwarded-*` (§29);
- иметь отдельный от desktop production-слой переменных окружения (§30);
- не использовать `%LOCALAPPDATA%` и рабочую директорию в hosted Linux
  (§31);
- сохранить удобный dev- и desktop-путь (§51).

## Решение

### 1. React: same-origin cookie, никаких Google-токенов, `401` → login

- `frontend/src/api.ts` сохраняет `const BASE = "/api"`, явно передаёт
  `credentials: "same-origin"` и не добавляет `Authorization`. Токены
  Google не попадают в `localStorage`, `sessionStorage`, IndexedDB, URL
  или React-state.
- Модуль имеет одну точку реакции на `401` (`setUnauthorizedHandler`);
  `DataContext` регистрирует её, очищает кэш и поднимает флаг
  `sessionRequired`. `AppShell` при `sessionRequired && !auth?.authenticated`
  рендерит `SignIn` до остального приложения. Reload сохраняет сессию,
  потому что cookie остаётся у браузера.
- Hosted-вход — полностраничная навигация `GET /api/auth/login`
  (серверный OAuth + callback). Desktop `POST /api/auth/login` остаётся
  loopback-флоу; hosted отвечает на него `405`, и фронтенд переходит по
  `LOGIN_URL` (§25/§26).

### 2. Явный environment-слой

`backend/config.py` читает:

| Переменная | Смысл |
| --- | --- |
| `APP_ENV` | `development` (default) или `production` |
| `APP_BASE_URL` | публичный HTTPS-origin; из него выводятся host и OAuth redirect URI |
| `GC_DASHBOARD_ALLOWED_HOSTS` | точный Host allow-list; при отсутствии — host из `APP_BASE_URL`, а в development ещё `localhost`/`127.0.0.1` |
| `GC_DASHBOARD_CORS_ORIGINS` | явные cross-origin фронтенды; `*` отбрасывается, пустой список — норма для production |
| `GC_DASHBOARD_TRUSTED_PROXIES` | IP/CIDR непосредственных reverse-proxy |
| `COOKIE_SECURE`, `COOKIE_SAMESITE` | флаги session-cookie |
| `GC_DASHBOARD_DATA_DIR` | override каталога данных |

`APP_BASE_URL` не хардкодится в других файлах: production-домен живёт в
одном env-значении (§28/§30).

### 3. Точная Host/Origin-валидация вместо hostname-only

- `Host`-header нормализуется общим парсером (`host_and_port_from_value`):
  port не входит в identity, IPv6, битые порты и мусор отклоняются.
- `Origin` сравнивается как **точный** нормализованный `scheme://host[:port]`
  с:
  1. `GC_DASHBOARD_CORS_ORIGINS`;
  2. `FRONTEND_ORIGINS` (только если `APP_ENV != production`);
  3. публичным origin самого запроса (`backend/proxy.py`).
  Совпадение только по hostname недостаточно: иначе `http://` и чужой
  port обходили бы same-origin-границу.
- Production по умолчанию не имеет CORS-списка и не доверяет localhost.
  Если cross-origin фронтенд нужен, он перечисляется точными origin-ами;
  `allow_origins=["*"]` с `allow_credentials=True` запрещён (§27).
- Guard добавлен **снаружи** `CORSMiddleware`, поэтому CORS-preflight с
  чужим Host/Origin получает `403`, а разрешённый cross-origin — обычные
  CORS-заголовки на `401/403`.

### 4. Trusted proxy — единственная точка доверия

`backend/proxy.py` — общий модуль для `main.py` и `hosted_auth.py`:

- `X-Forwarded-Proto` и `X-Forwarded-Host` принимаются, только если
  непосредственный peer входит в `GC_DASHBOARD_TRUSTED_PROXIES` (IP или
  CIDR). Недоверенный peer не может подменить схему cookie или host.
- `X-Forwarded-Host` дополнительно проверяется по `ALLOWED_HOSTS`; при
  ошибке запрос закрывается (`fail closed`), а не откатывается на Host.
- OAuth callback всегда строится из `APP_BASE_URL`, поэтому внутренний
  `http://127.0.0.1:8000/...` не может попасть в redirect (§29).
- `launcher.py` запускает Uvicorn с `proxy_headers=False`; иначе Uvicorn
  применил бы свой список (по умолчанию loopback) и переписал
  `request.client` до нашей проверки.

### 5. Cookie-флаги

Session-cookie: `HttpOnly`, `Path=/`, без `Domain`; `SameSite` из
`COOKIE_SAMESITE` (default `lax`); `Secure` берётся из `COOKIE_SECURE`,
иначе — из внешней схемы (trusted proxy). `SameSite=none` принудительно
включает `Secure`. Nonce-cookie OAuth-попытки всегда `Lax` и `HttpOnly`,
чтобы пережить cross-site redirect от Google.

### 6. Пути hosted-сервиса

`backend/path_config.py`: `GC_DASHBOARD_DATA_DIR` имеет высший приоритет;
hosted POSIX использует `/data`; только compiled desktop build берёт
`%LOCALAPPDATA%\GoogleClassHelp`; development — `<project>/data`. Ни один
production-путь не зависит от `Path.cwd()` (§31/§51).

### 7. Каноническая идентичность

`AuthStatus.user` — единственная форма личности; плоские
`user_name`/`user_email` удалены из схемы, API и generated frontend
schema. Пока сессии нет, `user = None` (в том числе в desktop-ветке).

### 8. Development vs production (§51)

Три слоя конфигурации разделены одним переключателем `APP_ENV`
(default `development`) и разными источниками секретов:

| Слой | Источник конфигурации | Секреты |
| --- | --- | --- |
| local development | дефолты `config.py`: loopback Host/CORS, SQLite в `<project>/data`, Vite-прокси на бэкенд | git-ignored `backend/credentials.json` (desktop-клиент); для hosted-разработки — отдельный **dev web-клиент** с redirect `http://localhost:5173/api/auth/callback` и `APP_BASE_URL=http://localhost:5173` |
| CI / тесты | `tests/conftest.py`: герметичный `GC_DASHBOARD_DATA_DIR`, фейковые значения env; фронтенд-тесты (vitest) секретов не читают | прод-секреты не требуются |
| production | `.env` по `.env.example`: `APP_ENV=production`, `APP_BASE_URL`, `GOOGLE_CLIENT_*`, `DATABASE_URL`, ключи | только env-контур; никогда в Git, образах, логах, ассетах |

Следования §51: локальная разработка не зависит от прод-базы
(`DATABASE_URL` читается только когда задан) и от прод-секретов
(hosted-эндпоинты fail closed при неполном клиентском конфиге, а не
падают на отсутствующем секрете); dev-режим не требует
`GC_DASHBOARD_ALLOWED_HOSTS`/`GC_DASHBOARD_CORS_ORIGINS` — их дефолты
уже loopback-корректны.

### 9. UI sync-состояния и UTC-таймстемпы (задачи этапов 5/6, закрыты здесь)

Схема `SyncStatus` (этап 5, §18) пришла в UI в этом этапе:

- `DataContext.syncing` = локальный `POST /api/sync` **или**
  `status.syncing` (queued либо running) — спиннер не зависит от того, кто
  запустил синк; единый watcher без фиксированного лимита опросов следит до
  terminal status и перечитывает cache;
- `sync_status === "error"` → ретрай-подсказка в TopBar с
  санитизированным `last_sync_error` в `title`; причина из БД, а не
  сырое исключение (§18);
- `sync_status === "needs_reauth"` → кнопка «войти снова» (hosted —
  серверный OAuth-redirect через `LOGIN_URL`) с подсказкой в Settings;
  расписание этого пользователя стоит на паузе, пока он не войдёт
  заново (§63);
- `last_sync` и остальные sync-таймстемпы — naive UTC: рендерятся через
  `dates.toLocalDate` (append `Z`) в локальной зоне браузера, а не
  `new Date(...)`, который читал бы их как локальное время.

## Последствия

- Плюс: hosted production живёт на одном origin, CORS минимален, host и
  схема приходят из env, а не из кода; desktop и Vite-разработка не
  затронуты.
- Плюс: единый trusted-proxy слой исключает расхождение между
  middleware и cookie-логикой; тесты фиксируют fail-closed-поведение.
- Минус/долг: политика CSRF, security headers, префикс `__Host-`,
  стратегия статики hosted (`Caddy` vs FastAPI) и HSTS — этап 8; они
  сознательно не входят в этап 7.
- `APP_ENV=production` без `APP_BASE_URL` не задаёт production-host
  автоматически: allow-list остаётся пустым (fail closed), а
  `GOOGLE_REDIRECT_URI` — пустым, пока не задан явно.
