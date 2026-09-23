# Этап 8 — Desktop and Hosted Coexistence: результат

Реализация этапа 8 миграции на хостинг
(`docs/migration/Desktop and Hosted Coexistence Part 1 num in query 8.md`,
§32–§38; `Part 2`, §48, §49, §50, §74, §75, §76). Опорные документы: аудит
`HOSTING_MIGRATION_AUDIT.md`, результаты этапов 2–7
(`HOSTING_MIGRATION_STAGE2.md`–`HOSTING_MIGRATION_STAGE7.md`), решение
`docs/adr/adr-0026-desktop-hosted-coexistence-production-edge.md`.

Дата: 2026-09-23. Все разделы промпта этапа 8 реализованы.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §32 | Убрать desktop-only код из hosted startup-пути | `main.py` импортирует `background_sync` только внутри desktop-ветки lifespan; новый `oauth_transport.py` — общий транспорт; `api.py`/`google_credentials.py` импортируют desktop-`auth` только внутри desktop-веток. Hosted-старт не загружает `launcher`/`background_sync`/`auth`/`pystray` (подпроцесс-тест) |
| §33 | Shared/desktop/hosted в одном репозитории | таблица слоёв в ADR-0026: shared (`oauth_transport`, `classroom_api`, `sync_*`, модели, `proxy`, `access_log`), desktop (`auth`, `background_sync`, `launcher`), hosted (`hosted_auth`, `google_credentials`, edge в `main.py`) |
| §34 | Один фронтенд | одно SPA; условного поведения два (hosted-redirect при 405, 401 → login-state); `import.meta.env`/VITE-ветвлений нет |
| §35 | Стратегия статики | **Option A**: FastAPI раздаёт `frontend/dist` (Caddy → FastAPI); пример Caddyfile в ADR-0026 |
| §36 | HTTPS обязателен | Caddy терминирует TLS; production hosted без `https://` в `APP_BASE_URL`/`GOOGLE_REDIRECT_URI` падает на старте; query redaction в `uvicorn.access` (`access_log.py`); `Cache-Control: no-store` на `/api` |
| §37 | Cookie-политика | `HttpOnly; Secure; SameSite=Lax; Path=/`, без Domain; TTL 14 суток, отзыв при logout; opt-in `__Host-`-префикс (`GC_DASHBOARD_COOKIE_HOST_PREFIX`) |
| §38 | CSRF | SameSite=Lax + точное совпадение Origin + Fetch Metadata (`Sec-Fetch-Site`) на unsafe-методах hosted; CORS защитой не считается; подписанный токен не введён (обоснование в ADR-0026) |
| §48 | Security headers | hosted: nosniff, Referrer-Policy, X-Frame-Options + `frame-ancestors 'none'`, same-origin CSP (inline-скрипт темы вынесен в `/theme-init.js`), HSTS opt-in `GC_DASHBOARD_HSTS_MAX_AGE` |
| §49 | Frontend security review | тест-скан источников и `dist` + ручной скан (см. §5); секретов в отслеживаемых исходниках нет |
| §50 | OAuth verification/branding | публичные `/privacy/` и `/terms/` (статика в `frontend/public/`, без сессии, без скриптов) |
| §74 | Desktop-поддержка intact | desktop-путь не тронут (ни headers, ни CSRF, ни lifespan); exe собирается тем же `build.bat`; смоук собранного exe — за владельцем (см. §7) |
| §75 | Раздельные redirect URI | desktop: динамический `http://127.0.0.1:<port>/` (`auth._CallbackServer`); hosted: фиксированный https из env; production-http запрещён (§36) |
| §76 | Разделение секретных доменов | desktop: base64-обфускация в exe (не граница безопасности); hosted: server-only env, никогда в браузере/dist/Nuitka/Git; `build.bat` встраивает только desktop-клиент |

## 2. Файлы

Добавлено:

- `backend/oauth_transport.py` — общий транспорт (scopes, обмен кода, refresh).
- `backend/access_log.py` — redaction query-строк `uvicorn.access` (§36).
- `tests/test_stage8_coexistence.py` — 16 тестов.
- `frontend/public/theme-init.js` — pre-paint скрипт темы (вне index.html, §48).
- `frontend/public/privacy/index.html`, `frontend/public/terms/index.html` (§50).
- `docs/adr/adr-0026-desktop-hosted-coexistence-production-edge.md`.

Изменено:

- `backend/auth.py` — только desktop loopback; транспорт переехал в
  `oauth_transport` (реэкспорт для совместимости).
- `backend/hosted_auth.py` — импорт транспорта из `oauth_transport`;
  имена cookie с opt-in `__Host-`-префиксом; §75 в docstring.
- `backend/google_credentials.py` — транспорт из `oauth_transport`,
  desktop-`auth` только лениво (§32).
- `backend/api.py` — desktop-`auth` только лениво (§32).
- `backend/main.py` — ленивый `background_sync`; CSRF fetch-check;
  security-headers middleware (hosted); `install_query_redaction()`;
  session-gate сужен до `/api/*` (см. §4); assets-404 с нормализацией
  сепараторов.
- `backend/config.py` — `HSTS_MAX_AGE`, `COOKIE_HOST_PREFIX`,
  production-https требование к redirect (§36).
- `frontend/index.html` — внешний `/theme-init.js` вместо inline-скрипта.
- `.env.example` — `GC_DASHBOARD_COOKIE_HOST_PREFIX`,
  `GC_DASHBOARD_HSTS_MAX_AGE`, комментарии §36/§48/§50.
- `tests/conftest.py` — герметичность stage-8 env.
- `tests/test_hosted_auth.py` — моки целятся в `oauth_transport`.
- `README.md` — раздел «Hosted production edge».
- `docs/adr/README.md` — зарегистрирован ADR-0026.

## 3. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| §32/§74 | hosted импортировал `background_sync` и desktop-`auth` | hosted не загружает `launcher`/`background_sync`/`auth`/`pystray` (тест); desktop-ветки ленивые |
| S1/S2 (остаток) | — | production edge только в hosted; desktop без headers (§74) |
| F1 (остаток) | inline-скрипт в index.html | внешний `/theme-init.js` — CSP без `unsafe-inline` для скриптов |
| — | session-gate закрывал и статику (401 на `/` без сессии) | гейт только на `/api/*`; SPA и `/privacy/`/`/terms/` публичны (§50) |
| — | `assets/*` без ведущего слеша отдавал index.html вместо 404 (Windows-пути) | нормализация сепараторов в SPA-fallback |

## 4. Тесты (162 всего, все зелёные; было 141)

Новые (`tests/test_stage8_coexistence.py`, 16):

- §32: hosted-старт без desktop-модулей (подпроцесс); desktop lifespan
  держит `background_sync`; desktop без security headers;
- §36: production-http redirect → отказ старта; https → ок; desktop без
  требования; redaction query-строк; установка фильтра один раз;
- §37: дефолтные имена/TTL cookie; `__Host-` opt-in (подпроцесс);
- §38: cross-site unsafe → 403; same-origin → 401 (гейт); safe-методы
  игнорируют Fetch Metadata; чужой Origin → 403;
- §48: headers на API и 401; HSTS только при env + https;
- §35/§50: legal-страницы существуют; Option A раздаёт их и SPA без
  сессии; assets-404;
- §49: скан источников (+ `dist`, когда собран) на секретные формы.

Обновлены: `test_hosted_auth.py` (моки на `oauth_transport`).

## 5. Проверки

- `pytest`: 162 passed (было 141).
- `ruff check` / `ruff format --check` (backend, tests, migrations): чисто.
- `pyright` (1.1.414, `pyrightconfig.json`): 0 errors.
- `npm run lint` (eslint + `tsc --noEmit`): чисто.
- `npx vitest run`: 51 passed.
- §49 ручной скан: `GOCSPX-|AIzaSy|BEGIN … PRIVATE KEY` — совпадения
  только в git-ignored локальных файлах (`backend/credentials.json`,
  `data/token.json` — dev desktop-клиент, в истории git не были, см.
  аудит этапа 2), в коде/фикстурах сторонних библиотек (`.venv`,
  `build/`) и в regex-паттернах нового теста. `git grep GOCSPX` по
  отслеживаемым файлам — только упоминание в аудите этапа 2.
  `git check-ignore` подтверждает: `data/`, `backend/credentials.json`,
  `build/`, `frontend/dist/` игнорируются. `gitleaks` CLI в среде
  отсутствует (как на этапе 7) — прогон в пайплайне остаётся за этапом 10.

## 6. Секреты: статус

Новых секретов нет; в отслеживаемых исходниках — только имена
env-переменных. Hosted-секрет (`GOOGLE_CLIENT_SECRET`, ключ Fernet)
по-прежнему только env; desktop-клиент — только локальный git-ignored
файл и base64 в exe (§76).

## 7. Что осталось за пределами этапа 8 (и почему)

- **Смоук собранного exe** (desktop-путь на `release\GoogleClassHelp.exe`):
  владелец собирает сам (`build.bat` не менялся); desktop-код этапа 8
  менялся только импортами, поведение покрыто существующими desktop-тестами
  (162 зелёных). При сборке проверить: SignIn-экран, вход, sync, трей.
- **Браузерный CSP-смоук** (CSP собрана под фактический бандл, но в среде
  нет браузера) и **включение HSTS** — этап 10 после подтверждения HTTPS.
- **Docker/Compose** (web + worker + Caddy + PostgreSQL), первый
  `alembic upgrade head` на живой БД, много-пользовательский смоук —
  этап 10.
- **Этап 9** (rate limits/capacity): пересчёт бюджетов sync против квот.
- Мелочь: контакт на privacy/terms — issues репозитория; владелец может
  заменить на email перед Google verification (§50).