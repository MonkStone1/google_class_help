# Этап 7 — Frontend and Configuration: cookie-сессия и 401, env-Host/CORS, trusted proxy, `/data`, §51

Реализация этапа 7 миграции на хостинг
(`docs/migration/Frontend and Configuration Part 1 num in query 7.md`,
§26–§31; `Frontend and Configuration Part 2 num in query 7.md`, §51).
Опорные документы: аудит `HOSTING_MIGRATION_AUDIT.md`, результаты этапов
2–6 (`HOSTING_MIGRATION_STAGE2.md`–`HOSTING_MIGRATION_STAGE6.md`), решение
`docs/adr/adr-0025-frontend-config-production.md`.

Дата: 2026-09-23. Все разделы промпта этапа 7 (§26–§31, §51) закрыты, а
также задачи UI, отложенные сюда из этапов 5 и 6 (спиннер
`sync_status`, рендер UTC-таймстемпов).

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §26 | `const BASE = "/api"` сохранён, same-origin cookie | `frontend/src/api.ts`: `credentials: "same-origin"`, `Authorization` не добавляется; токены Google не попадают в `localStorage`/`sessionStorage`/IndexedDB/URL/React-state (`SettingsContext` хранит только UI-настройки, ADR-0006) |
| §26 | на `401` — возврат в login-state | единая точка `setUnauthorizedHandler` в `api.ts`; `DataContext` при 401 сбрасывает `auth`/`status`/данные, ставит `sessionRequired` и сбрасывает teacher-кэш; `AppShell` при `sessionRequired && !authenticated` рендерит `SignIn` |
| §26 | reload сохраняет сессию | сессия — HttpOnly-cookie на своём origin; React ничего не хранит про неё |
| §26 | hosted-вход — redirect, не POST | `login()` ловит `405` от `POST /api/auth/login` и делает навигацию на `GET /api/auth/login` (`LOGIN_URL`) |
| §27 | same-origin без permissive CORS | production-дефолт `CORS_ORIGINS = ()`; `allow_origins=["*"] + allow_credentials=True` невозможен: `config._normalize_origins` отбрасывает `*` с предупреждением; точные cross-origin-фронтенды — только через `GC_DASHBOARD_CORS_ORIGINS` |
| §27 | убрать localhost-only допущения, сохранив host-guard | guard переписан: `main._host_allowed`/`_origin_allowed` работают от `ALLOWED_HOSTS`/`CORS_ORIGINS`/`APP_ORIGIN`; localhost допускается только в development (`FRONTEND_ORIGINS` учитывается вне production) |
| §28 | прод-домен из конфигурации, не хардкод | `GC_DASHBOARD_ALLOWED_HOSTS` → иначе host из `APP_BASE_URL`; production-дефолт = только `classroomhelp.pp.ua`-подобный host без loopback; dev добавляет `localhost`/`127.0.0.1`. Домен живёт в одном месте (`.env`) |
| §29 | trusted proxy, корректный внешний origin | новый `backend/proxy.py`: `X-Forwarded-Proto/Host` верят только пиру из `GC_DASHBOARD_TRUSTED_PROXIES` (IP/CIDR), `X-Forwarded-Host` дополнительно сверяется с `ALLOWED_HOSTS` (fail closed); OAuth callback строится из `APP_BASE_URL` — redirect на `http://127.0.0.1:8000/...` в проде невозможен; `launcher.py` — `proxy_headers=False`, чтобы Uvicorn не переписывал `request.client` до нашей проверки |
| §30 | явный production-слой переменных | `config.py`: `APP_ENV`, `APP_BASE_URL`, `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI` (redirect выводится из `APP_BASE_URL`), `GC_DASHBOARD_ALLOWED_HOSTS`, `GC_DASHBOARD_CORS_ORIGINS`, `GC_DASHBOARD_TRUSTED_PROXIES`, `COOKIE_SECURE`, `COOKIE_SAMESITE` (значение `none` принудительно включает `Secure`), `DATABASE_URL`, синк-переменные — все в `.env.example`; дублирующих независимых настроек нет; `.env` в `.gitignore` |
| §30 | `.env.example` только, секретов в Git нет | `.env.example` — плейсхолдеры; в коде — только имена переменных |
| §31 | пути hosted-сервиса | `path_config._resolve_data_dir()`: override `GC_DASHBOARD_DATA_DIR` → hosted POSIX `/data` (volume) → `%LOCALAPPDATA%` только для frozen desktop → `<project>/data` в dev; все пути абсолютные, `Path.cwd()` не используется; токены OAuth — в PostgreSQL (`oauth_tokens`), не в файловой системе контейнера |
| §51 | dev/CI/production разделены, dev OAuth-клиент | таблица слоёв в README («Конфигурация окружений») и в ADR-0025 §8: development — дефолты `config.py` + git-ignored `credentials.json` (desktop) или отдельный dev web-клиент с redirect `http://localhost:5173/api/auth/callback` для hosted-разработки; CI/тесты — герметичный `tests/conftest.py`, фронтенд-тесты секретов не требуют; production — `.env`. Прод-база локальной разработкой не используется |
| §51 | фронтенд-тесты без прод-секретов | vitest идёт без какого-либо env; backend-тесты создают свой `GC_DASHBOARD_DATA_DIR` и фейковые значения (в т.ч. `COOKIE_*`, `APP_*`) |
| — (этап 5, §18) | UI sync state: спиннер/ретрай/«войдите снова» | `DataContext.syncing` теперь `локальный sync ИЛИ status.syncing` (queued/running), единый watcher обновляет cache после terminal status; `error` → ретрай-подсказка в TopBar с санитизированным `last_sync_error` в `title`; `needs_reauth` → кнопка «войти снова» (hosted — серверный OAuth-redirect) + подсказка в Settings; новые ключи `topbar.signInAgain`/`topbar.needsReauthHint` (en/ru/uk) |
| — (этап 5, §18) | рендер UTC `last_sync` в локальной зоне | `dates.toLocalDate`: naive-UTC бэкенда читается как UTC (append `Z`), значения со смещением — как есть, мусор → `null`; используется в TopBar `SyncTime` и Settings (раньше `new Date(...)` читал naive-UTC как локальное время) |
| — (этап 6, §24) | одна форма личности | плоские `user_name`/`user_email` удалены из `schemas.AuthStatus`, `hosted_auth`, `api` и generated `api-schema.d.ts`; UI читает `AuthStatus.user` |

## 2. Файлы

Добавлено:

- `backend/proxy.py` — trusted-proxy слой (§29): `peer_is_trusted_proxy`,
  `external_scheme`, `effective_authority`, `public_origin`; общий для
  `main.py` и `hosted_auth.py`.
- `tests/test_stage7_frontend_config.py` — 26 тестов (§26–§31).
- `docs/adr/adr-0025-frontend-config-production.md` — решение этапа 7
  (включая §51 и UI sync-состояния).

Изменено:

- `backend/config.py` — environment-слой (§28–§30): `APP_ENV`/
  `IS_PRODUCTION`, `APP_BASE_URL`/`APP_ORIGIN`, нормализация origins и
  host-значений (`_normalize_origins`, `host_and_port_from_value`,
  `canonical_origin`), `ALLOWED_HOSTS`, `CORS_ORIGINS`, `TRUSTED_PROXIES`,
  `COOKIE_SECURE`/`COOKIE_SAMESITE` (tri-state `_bool_env`), redirect URI
  из `APP_BASE_URL`.
- `backend/main.py` — guard по конфигурации вместо `TRUSTED_HOSTS`
  (`_host_allowed`, `_request_host_allowed`, `_origin_allowed`), порядок
  middleware: CORS → Host/Origin-guard → session-gate; guard работает в
  обоих режимах.
- `backend/path_config.py` — `HOSTED_DATA_DIR = /data`,
  `_resolve_data_dir()` (§31) и docstring про отсутствие зависимости от
  рабочей директории.
- `backend/hosted_auth.py` — cookie-флаги через общий proxy-слой
  (`_session_cookie_secure`), `COOKIE_SAMESITE` из env.
- `backend/launcher.py` — Uvicorn с `proxy_headers=False` (§29).
- `.env.example` — §30/§51-переменные с комментариями (Host/CORS/proxy,
  cookie-флаги, `APP_ENV`).
- `frontend/src/api.ts` — `LOGIN_URL`, единый обработчик 401, явный
  `credentials: "same-origin"`.
- `frontend/src/context/DataContext.tsx` — `sessionRequired` (401 →
  login-state, кэш сбрасывается), hosted-навигация на `LOGIN_URL` при 405,
  `syncing` учитывает queued/running через `status.syncing` и автоматически
  обновляет cache после terminal status.
- `frontend/src/App.tsx`, `frontend/src/components/SignIn.tsx` — гейт по
  `sessionRequired && !authenticated`.
- `frontend/src/components/TopBar.tsx`, `frontend/src/pages/Settings.tsx` —
  рендер `last_sync` через `toLocalDate`, ретрай-подсказка
  (`last_sync_error`), `needs_reauth`-кнопка/подсказка, идентичность из
  `auth.user`.
- `frontend/src/dates.ts` — исправлен `toLocalDate` (naive-UTC → `Z`),
  `frontend/src/dates.test.ts` — 3 новых теста.
- `frontend/src/i18n/{en,ru,uk}.ts` — `topbar.signInAgain`,
  `topbar.needsReauthHint`.
- `frontend/openapi.json`, `frontend/src/api-schema.d.ts` —
  перегенерированы под `AuthStatus.user` и `SyncStatus`.
- `README.md` — раздел «Конфигурация окружений (§51)».
- `tests/test_user_isolation.py` — `assert state.user is not None` перед
  обращением к полям (pyright `reportOptionalMemberAccess`).
- `docs/adr/README.md` — зарегистрирован ADR-0025.

## 3. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| S1 | `TRUSTED_HOSTS = ("127.0.0.1","localhost")` + `enforce_local_only` | `ALLOWED_HOSTS` из env/`APP_BASE_URL`; production — только публичный домен, development — loopback |
| S2 | CORS `allow_origins=FRONTEND_ORIGINS` (localhost) | `CORS_ORIGINS`: production по умолчанию пуст, dev — Vite-origins; wildcard запрещён |
| C3 | `FRONTEND_ORIGINS = [localhost:5173]` зашит в код | dev-дефолт остался для удобства, но production-значения приходят из env; домен — одно значение `APP_BASE_URL` |
| F1 | логин — POST, фронтенд не знает redirect | hosted: `GET /api/auth/login` через `LOGIN_URL`; 401 → login-state |
| F2 | гейтинг только по `status.authenticated`, нет cookie-сессий | `sessionRequired` от 401, cookie — серверная, reload сохраняет вход |
| F3 | сетевые ошибки = «бэкенд недоступен» | 401 отделён от сетевой ошибки (`isUnauthorized`); 401 сбрасывает данные и уводит в login, сетевая ошибка остаётся fallback на кэш |
| T1 | тесты с зашитыми localhost-допущениями | Host/Origin-тесты параметризуются через monkeypatch `ALLOWED_HOSTS`/`CORS_ORIGINS`; добавлены таблицы dev/production-дефолтов |

## 4. Тесты

**Backend: 141 всего, все зелёные** (было 115 после этапа 6).

Новые — `tests/test_stage7_frontend_config.py` (26):

- environment-слой: production-дефолт Host = только публичный host; dev
  добавляет loopback; wildcard CORS отбрасывается, origins нормализуются
  (порт/регистр); булев `COOKIE_*`-значение — «не задан», а не `false`;
  `COOKIE_SAMESITE=none` включает `COOKIE_SECURE`; production-окружение
  выводит `ALLOWED_HOSTS`/`CORS_ORIGINS`/`APP_ORIGIN`/redirect URI из
  одного `APP_BASE_URL` (запуск в подпроцессе с чистым env);
- Host/Origin-guard: port/регистр игнорируются, битый порт и запятые в
  Host — отказ; Origin сравнивается по точной схеме+порту (`http://` и
  чужой порт ≠ origin), `null` и origin с путём — отказ; production не
  пускает `localhost:5173` без явной CORS-записи, development пускает;
  preflight с чужим Host/Origin — 403 до CORS-Responder, разрешённый
  cross-origin — `access-control-allow-origin/credentials`, same-origin —
  200 без CORS-записи;
- trusted proxy: заголовки от недоверенного пира игнорируются; доверенный
  пир задаёт схему/host; запрещённый `X-Forwarded-Host` → `None` (fail
  closed); битые записи списка игнорируются;
- cookie-флаги: явный `COOKIE_SECURE` побеждает, иначе Secure следует за
  внешней схемой **только** от настроенного прокси;
- пути: override `GC_DASHBOARD_DATA_DIR` побеждает во всех режимах;
  hosted POSIX → `/data`; frozen desktop → `%LOCALAPPDATA%`;
- граница браузера: hosted data-ручки без сессии → 401; `POST
  /api/auth/login` → 405, `GET` → 302 на Google.

**Frontend: 51 тест (7 файлов), все зелёные** (vitest); 3 новых —
`toLocalDate`: naive-UTC читается как UTC, значения со смещением
сохраняются, мусор → `null`.

Обновлён: `tests/test_user_isolation.py` (гард `state.user is not None`
для pyright).

## 5. Проверки

- `pytest`: 141 passed (было 115).
- `ruff check` / `ruff format --check` (`backend`, `tests`, `migrations`):
  чисто. (`tools/make_icon.py` и markdown-документы вне этой выборки —
  не менялись в этом этапе.)
- `pyright` (npx, `pyrightconfig.json`): 0 errors.
- `npm run lint` (eslint + `tsc --noEmit`): чисто.
- `npx vitest run`: 51 passed.
- Секретов в отслеживаемых исходниках не появилось: в новых файлах —
  только имена env-переменных; `.env.example` — плейсхолдеры.
  `gitleaks` в этой среде отсутствует (CLI не установлен) — прогон
  проектного `.gitleaks.toml` перенесён на этап 10.

## 6. Что осталось за пределами этапа 7 (и почему)

- **Этап 8 (desktop coexistence / security):** CSRF-политика, security
  headers, `__Host-`-префикс session-cookie, HTTPS/HSTS, стратегия
  раздачи статики (Caddy vs FastAPI) — сознательно вне §26–§31; смоук
  desktop-пути на собранном exe.
- **Этап 9 (rate limits/capacity):** пересчёт
  `SYNC_MAX_WORKERS × SYNC_MAX_CONCURRENT_USERS` против Google-квот.
- **Этап 10 (деплой):** Docker/Compose (`/data`-volume, web + worker),
  первый `alembic upgrade head` на живом PostgreSQL, много-пользовательский
  смоук, README-раздел хостед-развёртывания, прогон gitleaks в пайплайне.
- Мелочь: `sync_status` читается из `/api/status` при загрузке и после
  синка/refresh — фоновый переход `running → ok` подхватится ближайшим
  обновлением статуса, а не поллингом; поллинг статуса в UI не вводился
  (не требуется промптом; при необходимости — на этапе 10).
</parameter>
<task_progress>
- [x] Прочитать аудиты и промпт этапа 7
- [x] Проверить, что уже сделано по §26–§31, §51
- [x] sync UI: спиннер queued/running, needs_reauth, UTC-рендер last_sync (+ тесты)
- [x] Документация §51 (dev/CI/prod конфигурации) — README
- [x] Аудит этапа 7 (HOSTING_MIGRATION_STAGE7.md) + §51 в ADR-0025
- [ ] Прогнать финальные проверки (pytest, ruff, pyright, npm lint, vitest)
</task_progress>
</write_to_file>