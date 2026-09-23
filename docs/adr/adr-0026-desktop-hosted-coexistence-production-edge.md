# ADR-0026 — Desktop/hosted coexistence и production edge (этап 8)

Статус: Accepted. Этап 8 миграции (`Desktop and Hosted Coexistence`,
§32–§38, §48–§50, §74–§76). Опорные документы: аудит
`docs/migration/audits/HOSTING_MIGRATION_AUDIT.md`, результаты этапов 2–7,
тесты `tests/test_stage8_coexistence.py`.

## 1. Контекст

К этапу 8 модель приложения уже мультиюзерная (web OAuth + сессии,
PostgreSQL, user-scoping, per-user sync), но:

- hosted-старт всё ещё импортировал desktop-модули (`background_sync` на
  верхнем уровне `main.py`; desktop loopback-код `auth.py` — через
  `api.py`/`hosted_auth.py`/`google_credentials.py`);
- production edge отсутствовал: security headers, CSRF-политика, HSTS,
  `__Host-`-префикс, redaction логов, публичные privacy/terms-страницы;
- session-gate закрывал вообще всё, включая статику — SPA-оболочка и
  публичные страницы отдавали 401 без сессии (найдено тестом этапа 8,
  исправлено здесь).

## 2. Решение: разделение модулей (§32/§33/§74)

```text
shared business logic
        │
   ┌────┴─────┐
   │          │
Desktop      Hosted Web
```

| Слой | Модули | Правило импорта |
| --- | --- | --- |
| Shared | `oauth_transport.py` (scopes, обмен кода, refresh), `classroom_api.py`, `sync_*`, `models*`, `schemas.py`, `grading.py`, `proxy.py`, `access_log.py` | оба режима |
| Desktop | `auth.py` (loopback OAuth, ADR-0019), `background_sync.py`, `launcher.py` (mutex/tray/browser/Nuitka) | только desktop-путь, лениво |
| Hosted | `hosted_auth.py` (web OAuth + сессии), `google_credentials.py` (per-user слой), security edge в `main.py` | только hosted-путь |

Конкретно:

- новый `oauth_transport.py` — scopes (ADR-0002), `post_token_request`,
  `credentials_from_payload`, `refresh_credentials`. `auth.py` держит
  только desktop loopback и реэкспортирует транспорт для совместимости
  (tools/tests);
- `main.py` импортирует `background_sync` только внутри desktop-ветки
  lifespan; `api.py` и `google_credentials.py` импортируют `auth` только
  внутри desktop-веток;
- hosted-старт не загружает `launcher`/`background_sync`/`auth`/`pystray`
  — проверяется подпроцесс-тестом
  (`test_hosted_startup_imports_no_desktop_module`);
- desktop-путь не тронут: ни security headers, ни CSRF-проверки, ни
  lifespan desktop-ветки (§74; `test_desktop_app_has_no_security_headers`).

## 3. Один фронтенд (§34)

Одно React SPA на оба режима. Условного поведения два, оба runtime:

- hosted-вход — redirect: `POST /api/auth/login` отвечает 405, фронтенд
  переходит на `GET /api/auth/login` (этап 7);
- 401 → login-state (этап 7).

В коде нет `import.meta.env`/VITE-ветвлений и нет второй сборки.

## 4. Статика: Option A (§35)

Выбран **Option A — FastAPI раздаёт собранный SPA**:

```text
Caddy (TLS, HTTP→HTTPS)
  └── FastAPI (uvicorn)
        ├── /api/*  → API routes
        └── /       → frontend/dist (SPA fallback; /privacy/, /terms/ — index)
```

Пример Caddyfile (этап 10 уточнит имена сервисов):

```caddy
monkstonecor.pp.ua {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy по умолчанию терминирует TLS и редиректит HTTP→HTTPS. Option B
(Caddy раздаёт статику) отклонён: он дублирует SPA-fallback и
версионирование ассетов без выигрыша для этого проекта.

## 5. HTTPS (§36)

- Production hosted отказывается стартовать без HTTPS: `config.py`
  требует `https://` у `APP_BASE_URL`/`GOOGLE_REDIRECT_URI` при
  `APP_ENV=production + GC_DASHBOARD_HOSTED=1` (RuntimeError на импорте).
- Desktop loopback остаётся `http://127.0.0.1:<port>/` — это корректно и
  отдельно (§75).
- Query-строки вырезаются из `uvicorn.access` (`access_log.py`): callback
  `?code=…&state=…` в лог не попадает. Свои логи кодов/токенов код и так
  не пишет (этапы 2–7).
- `/api`-ответы несут `Cache-Control: no-store` — per-user данные не
  оседают в кэшах.

## 6. Cookie-политика (§37)

`gch_session` (+ `gch_oauth_nonce`): `HttpOnly; Secure; SameSite=Lax;
Path=/`, без Domain — ровно набор ограничений префикса `__Host-`.
TTL сессии 14 суток, явное истечение, отзыв при logout (этап 2);
постоянных сессий нет. Opt-in `GC_DASHBOARD_COOKIE_HOST_PREFIX=1` даёт
`__Host-gch_session` (требует `COOKIE_SECURE=true`, иначе браузер
отклонит cookie — предупреждение в config).

## 7. CSRF (§38)

State-changing ручки: `POST /api/auth/logout`, `POST /api/sync`,
`DELETE /api/cache` (будущие write — под ту же политику). Слои:

1. `SameSite=Lax` cookie (§37);
2. точное совпадение Origin (этап 7, §27) — cross-site unsafe-запрос
   браузера всегда несёт Origin;
3. Fetch Metadata для запросов без Origin: `Sec-Fetch-Site` вне
   `same-origin`/`none` → 403 (hosted, unsafe-методы). Оба заголовка
   отсутствуют = не браузер (нет ambient cookie jar) — разрешено, чтобы
   не ломать API-инструменты.

CORS сознательно НЕ считается CSRF-защитой. Подписанный CSRF-токен не
введён: при host-only cookie + SameSite=Lax + проверке Origin каждого
unsafe-запроса он не даёт выигрыша; пересмотреть, если SameSite будет
ослаблен или появится cross-origin фронтенд.

## 8. Security headers (§48)

Hosted-режим (desktop не трогаем, §74):

- `X-Content-Type-Options: nosniff`,
- `Referrer-Policy: strict-origin-when-cross-origin`,
- `X-Frame-Options: DENY` + `frame-ancestors 'none'`,
- CSP: всё same-origin (`script-src 'self'` без inline-исключений —
  pre-paint скрипт темы вынесен в `/theme-init.js`; `style-src` держит
  `'unsafe-inline'` для React inline-стилей). Внешних origin'ов бандл не
  требует: в исходниках нет внешних URL (§49), Google OAuth — серверный
  302, а не fetch/frame;
- HSTS — opt-in `GC_DASHBOARD_HSTS_MAX_AGE` (0 = выкл), только на
  внешне-https запросах; включать после подтверждения HTTPS (этап 10).
  Если заголовок ставит Caddy — оставить env на 0 (без дублей).

CSP не тестировалась в браузере (в среде его нет): политика собрана под
фактический бандл (проверены index.html, public/, отсутствие внешних
ресурсов), браузерный смоук — на этапе 10.

## 9. Frontend security review (§49)

- Источники (`src/`, `public/`, `index.html`) и собранный `dist` (когда
  есть) сканируются тестом `test_frontend_sources_contain_no_secret_material`
  (формы `GOCSPX-`, `AIzaSy…`, PEM-ключи, `client_secret=`-значения, DSN).
- Ручной скан: секреты есть только в git-ignored локальных файлах
  (`backend/credentials.json`, `data/token.json` — dev desktop-клиент,
  в истории git не были) и в коде/фикстурах сторонних библиотек
  (`.venv`, `build/` — не наши секреты). В отслеживаемых исходниках —
  только имена env-переменных; `git grep GOCSPX` по треку даёт лишь
  упоминание в аудите этапа 2.
- `frontend/dist` публичен по определению: туда не попадает ничего, кроме
  сборки (секреты — только env сервера, §76).

## 10. OAuth verification / branding (§50)

Публичные страницы (без сессии, вне session-gate — гейт закрывает только
`/api/*`, см. §11):

- `https://monkstonecor.pp.ua/privacy/` — Privacy Policy,
- `https://monkstonecor.pp.ua/terms/` — Terms of Service.

Статический HTML в `frontend/public/{privacy,terms}/index.html` (без
скриптов — рендерятся под `script-src 'self'`), раздаются Option A.
Контакт для privacy/deletion — issues проектного репозитория (владелец
может заменить на email перед verification).

## 11. Исправление: session-gate закрывал статику

До этапа 8 гейт требовал сессию на любом пути, кроме `/api/health` и
`/api/auth/*` — то есть и на `/`, `/privacy/`, ассетах. Hosted-вход был
бы невозможен: оболочка с экраном SignIn не загружалась бы без сессии.
Гейт сужен до `/api/*` (тест `test_static_strategy_option_a_…`); data-ручки
по-прежнему 401 без сессии (тесты этапов 2/4 не менялись и зелёные).

## 12. Redirect URI и секретные домены (§75/§76)

- Desktop: `http://127.0.0.1:<свободный порт>/` — строится динамически
  `_CallbackServer` в `auth.py` (ADR-0019).
- Hosted: фиксированный `https://<домен>/api/auth/callback` из
  `APP_BASE_URL`/`GOOGLE_REDIRECT_URI` (env). Реализации не пересекаются;
  desktop-клиент (тип Desktop app) и hosted-клиент (тип Web application) —
  разные клиенты GCP.
- Секреты: desktop — base64-обфускация в exe (`build_secrets.py`), только
  от случайного взгляда, не граница безопасности; hosted — server-only
  env (`GOOGLE_CLIENT_SECRET`, ключ Fernet), никогда в браузере, `dist`,
  Nuitka-артефактах и Git. Nuitka-билд (`build.bat`) встраивает только
  desktop-клиент и не читает hosted env.

## 13. Последствия

- Hosted-деплой импортирует только нужное; desktop exe собирается тем же
  `build.bat` без изменений (смоук — в аудите этапа).
- Браузерный CSP-смоук и включение HSTS — этап 10 (деплой).
- CSRF-токен — только если ослабнет SameSite или появится cross-origin
  фронтенд.