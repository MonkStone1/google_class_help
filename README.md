# Local Google Classroom Dashboard

Локальный дашборд Google Classroom: FastAPI + SQLite-кэш на бэкенде,
React (Vite) на фронтенде. Работает только на localhost, данные синхронизируются
с Google Classroom API (read-only scopes, см. `docs/adr/adr-0002`).

Два режима работы: **разработка** (два процесса: uvicorn + Vite dev-сервер)
и **production** (один exe-файл `GoogleClassHelp.exe` на Nuitka).

---

## DEVELOPMENT

Требования: Python 3.13 (`.venv`), Node.js + npm.

### Backend

```bat
cd D:\Documents\google_class_help
.venv\Scripts\activate
cd backend
uvicorn main:app --reload
```

Бэкенд: <http://127.0.0.1:8000> (Swagger: `/docs`).

### Frontend

```bat
cd D:\Documents\google_class_help\frontend
npm install
npm run dev
```

Vite dev-сервер: <http://localhost:5173> — проксирует `/api` на бэкенд
(см. `frontend/vite.config.ts`). Работать надо именно через `:5173`.

### OAuth в разработке

- положите OAuth-клиент (тип *Desktop app*) из Google Cloud Console в
  `backend/credentials.json` (файл git-ignored);
- токен после первой авторизации появится в `data/token.json`
  (git-ignored; каталог можно переопределить через `GC_DASHBOARD_DATA_DIR`).

### Конфигурация окружений (миграция на хостинг, §51)

Три слоя конфигурации разделены; прод-секреты не нужны ни для
разработки, ни для тестов:

| Слой | Запуск | Конфигурация |
| --- | --- | --- |
| **Local development** | `uvicorn main:app --reload` + `npm run dev` (как выше) | по умолчанию `APP_ENV=development`: Host-список — `localhost`/`127.0.0.1`, CORS — Vite-origins, БД — SQLite в `<проект>\data\`. Прод-переменные (`DATABASE_URL`, секреты Google) не читаются |
| **Hosted-разработка** (опционально) | те же команды + `GC_DASHBOARD_HOSTED=1` и `APP_BASE_URL=http://localhost:5173` | отдельный **development web OAuth-клиент** Google с redirect `http://localhost:5173/api/auth/callback` (Vite проксирует `/api` на бэкенд); локальный PostgreSQL или `DATABASE_URL` локального инстанса — прод-база не используется |
| **CI / тесты** | `pytest`, `ruff`, `pyright`, `npm run lint`, `npx vitest run` | герметично: `tests/conftest.py` поднимает свой `GC_DASHBOARD_DATA_DIR` и подставляет фейковые значения env; фронтенд-тесты (vitest) секретов не требуют вообще |
| **Production** | Docker/Compose (этап 10) | `.env` по `.env.example`: `APP_ENV=production`, `APP_BASE_URL`, web-клиент Google, `DATABASE_URL` (PostgreSQL), ключи шифрования. Секреты — только в env, никогда в Git и в ассетах |

Правила: локальная разработка **не зависит** от прод-базы и прод-секретов;
для Google OAuth в разработке используйте отдельный dev-клиент, а не
production web-клиент (`APP_ENV` и `GC_DASHBOARD_ALLOWED_HOSTS`/
`GC_DASHBOARD_CORS_ORIGINS` не задаются — дефолты development-режима).

### Hosted production edge (миграция на хостинг, этап 8, ADR-0026)

- Статика — Option A: FastAPI раздаёт `frontend/dist` (Caddy → FastAPI);
  session-gate закрывает только `/api/*`, оболочка SPA и публичные
  страницы доступны без сессии.
- HTTPS обязателен: Caddy терминирует TLS и редиректит HTTP→HTTPS;
  production hosted без `https://` в `APP_BASE_URL` не стартует.
- Security headers (только hosted): `nosniff`, `Referrer-Policy`,
  `X-Frame-Options`, same-origin CSP, `no-store` на `/api`; HSTS — opt-in
  `GC_DASHBOARD_HSTS_MAX_AGE` после подтверждения HTTPS (этап 10).
- Cookie `gch_session`: HttpOnly/Secure/Lax, `Path=/`, без Domain, TTL 14
  суток; opt-in `__Host-`-префикс (`GC_DASHBOARD_COOKIE_HOST_PREFIX=1`).
- CSRF: SameSite=Lax + точный Origin + Fetch Metadata на unsafe-методах
  (`POST /api/auth/logout`, `POST /api/sync`, `DELETE /api/cache`); CORS
  защитой не считается, подписанный токен не требуется (см. ADR-0026).
- Публичные страницы для Google OAuth verification: `/privacy/`, `/terms/`.
- Секреты: desktop-клиент встраивается в exe (base64 — обфускация, не
  защита); hosted-секрет (`GOOGLE_CLIENT_SECRET`, ключ Fernet) — только
  env сервера, никогда в браузере, `frontend/dist`, Nuitka-артефактах и Git.

### Rate limits, capacity и retention (миграция на хостинг, этап 9, ADR-0027)

- **Лимиты (только hosted):** токен-бакеты по (поверхность, client IP) —
  логин 30/мин, отклонённые OAuth-callback'и 20/мин, ручной синк 60/мин
  **плюс cooldown 60 с на пользователя**, очистка кэша 10/мин; превышение
  → 429 + `Retry-After`. IP из `CF-Connecting-IP`/`X-Forwarded-For`
  верится только от доверенного прокси. Desktop не лимитируется.
  Прод-`.env` для 1 vCPU / 1 GB ставит консервативнее: логин 10/мин, синк
  10/мин.
- **Бюджет синка:** `SYNC_MAX_WORKERS` × `SYNC_MAX_CONCURRENT_USERS`;
  на целевом VPS 1 vCPU / 1 GB это `2 × 1 = 2` потока, интервал 30 мин,
  стартовый stagger 600 с — очередь вместо залпа. Арифметика в
  `backend/capacity.py`; рост лимитов — только вместе со счётчиками
  `quota_errors`/`server_errors` в логе синка.
- **Ручной синк — queued:** `POST /api/sync` только ставит
  `sync_requested` и сразу отвечает `{"ok": true, "queued": true}`;
  работу выполняет воркер. Уже идущий синк → 409, cooldown → 429.
  Desktop сохраняет inline-поведение (503 при исчерпании пула).
- **Токены Google:** `invalid_grant` удаляет грант только этого
  пользователя и ставит `needs_reauth`; остальные аккаунты не затрагиваются.
- **Логи hosted:** stdout (Docker/systemd), с редакцией query-строк и
  redaction-фильтром токенов/куки/секретов; desktop — `%LOCALAPPDATA%` как
  раньше.
- **Retention и удаление:** воркер вычищает просроченные сессии и
  OAuth-попытки (`GC_DASHBOARD_RETENTION_SWEEP_SECONDS`); пути удаления —
  `DELETE /api/me/google` (отвязать Google) и `DELETE /api/me` (аккаунт со
  всем кэшем), оба с `confirm=true` и только про вызывающего;
  `DELETE /api/me/cache` — явный алиас очистки кэша.
- **Транзакции:** синк не держит соединение PostgreSQL через сетевой фетч
  (короткие транзакции на фазы); пул `3+2` соединений на 1 vCPU / 1 GB.

### Развёртывание на хостинге (миграция этап 10, ADR-0028)

Прод — пять контейнеров на приватной docker-сети, наружу ничего:

```text
Internet → Cloudflare (TLS, DDoS) → Tunnel → cloudflared
                                                 ↓
                                            caddy:80 → web:8000 → postgres:5432
                                                       worker  → postgres:5432
```

Ключевые файлы: `Dockerfile` (Node-сборка фронта + python:3.12-slim,
non-root, pinned `backend/requirements-prod.txt`), `compose.yml`,
`Caddyfile` (внутренний HTTP-хоп, `max_size 2MB`), `.dockerignore`,
`tools/backup_postgres.sh`, `.env.example`.

Порядок выката и приёмка — `docs/DEPLOYMENT_CHECKLIST.md`
(Cloudflare → VPS/firewall → `.env` → `docker compose build` →
`alembic upgrade head` → health/ready → OAuth → изоляция → бэкапы).

- **Health/readiness:** `GET /api/health` (публичный, `{"ok": true}`) и
  `GET /api/ready` (`SELECT 1`, 200/503, без деталей инфраструктуры) —
  используются healthcheck'ом контейнера и туннелем.
- **Origin скрыт:** публичных портов у VPS нет, PostgreSQL и uvicorn
  доступны только внутри `internal`-сети; SSH — по ключам.
- **Бэкапы:** `pg_dump --format=custom` в `backups/` (rolling 7), restore
  останавливает web/worker, затем `alembic upgrade head`; `.env`
  (Fernet-ключ, Google secret, tunnel token) хранится отдельно и
  зашифрованно, дампы никогда не попадают в Git.
- **Turnstile** реализован и включается заполнением
  `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY` (пустые ключи — проверка
  выключена); **HSTS включён** (`GC_DASHBOARD_HSTS_MAX_AGE=31536000`,
  только по https).


---

## PRODUCTION BUILD

Production-сборка превращает проект в один файл `GoogleClassHelp.exe`:
FastAPI + встроенный фронтенд из `frontend/dist` + OAuth-клиент,
вшитый в бинарник (обфусцированный, без plaintext `credentials.json`).

Требования: то же, что для разработки + установленный в `.venv` Nuitka
(`.venv\Scripts\pip install nuitka`) и компилятор MSVC (Visual Studio Build
Tools); при их отсутствии Nuitka скачает MinGW64 сама
(`--assume-yes-for-downloads`).

### Сборка одной командой

```bat
build.bat
```

Скрипт выполняет:

1. чистит и пересобирает фронтенд: `npm run build` → `frontend/dist`;
2. встраивает OAuth-клиент: `backend/build_secrets.py` генерирует
   `backend/embedded_secrets.py` (XOR+base64 со случайным ключом) из
   `backend/credentials.json`;
3. генерирует иконку `assets/GoogleClassHelp.ico` (tools/make_icon.py);
4. компилирует `backend/launcher.py` в no-console onefile exe через Nuitka
   (фронтенд включается через `--include-data-dir=frontend/dist=frontend/dist`);
5. копирует результат в `release\GoogleClassHelp.exe`.

Ручной запуск этапов см. в самом `build.bat`.

### Где что лежит после сборки

| Артефакт | Путь |
| --- | --- |
| Итоговый exe | `release\GoogleClassHelp.exe` |
| Промежуточные файлы Nuitka | `build\` (можно удалять) |

### Запуск и тест release-сборки

1. Двойной клик `release\GoogleClassHelp.exe` (или запуск из терминала —
   консольное окно не появится).
2. Бэкенд стартует на `http://127.0.0.1:8000`; если порт занят чужим
   процессом — выбирается соседний свободный, браузер открывается на
   фактическом порту. Если exe уже запущен, второй инстанс **не** создаётся:
   запуск активирует работающий дашборд (фокус уже открытого окна, новая
   вкладка — только если окна нет) и завершается (ADR-0018). Если дашборд
   открыт в закреплённой/фоновой вкладке (её не видно в заголовке окна),
   новая вкладка показывает уведомление «дашборд уже открыт» с кнопкой
   *Switch to it*: переключение выполняется через service worker, потому что
   браузеры перемещают вкладку только при свежем клике — если автопопытка не
   удалась, достаточно нажать кнопку; при неудаче подсказка предложит закрыть
   вкладку вручную.
3. После старта в системном трее появляется иконка: **Open dashboard**
   (двойной клик) и **Exit**. Прячется она вместе с выходом приложения;
   без `pystray`/`Pillow` приложение работает как раньше, без иконки.
4. Для чистого теста «на машине без проекта»: скопируйте
   `release\GoogleClassHelp.exe` на любую машину с Windows и запустите.
   Нужен только доступ в интернет (Google OAuth/API).
5. Логи: `%LOCALAPPDATA%\GoogleClassHelp\logs\app.log`.

### Первый запуск / OAuth

- При отсутствии токена бэкенд поднимется, но данные появятся после
  авторизации: в дашборде нажмите вход — откроется браузер с согласием
  Google (read-only Classroom scopes, ADR-0002), токен сохранится в
  `%LOCALAPPDATA%\GoogleClassHelp\token.json`.
- Повторные запуски используют и обновляют существующий токен.
- Если браузер не открылся автоматически (например, при запуске exe под
  Wine), ссылка на страницу согласия есть в настройках дашборда и в
  `logs/app.log`: вход можно завершить по ней (ADR-0019).
- Обмен кода и обновление токена идут через httplib2 — тот же транспорт,
  которым ходят запросы к Classroom API; `requests`/`urllib3` остаётся первой
  попыткой, но его сбой больше не блокирует вход (ADR-0019).
- Проверить флоу без браузера: `.venv\Scripts\python.exe tools\check_oauth_flow.py`
  (поддельный код → Google отвечает `invalid_grant`).

### Хранение пользовательских данных (production)

```text
%LOCALAPPDATA%\GoogleClassHelp\
├── token.json        — OAuth-токен пользователя (не входит в exe)
├── classroom.db      — SQLite-кэш Classroom
├── app.lock          — pid/порт работающего инстанса (ADR-0018)
└── logs\app.log      — лог приложения (ротация 1 МБ × 3)
```

Каталог можно переопределить переменной `GC_DASHBOARD_DATA_DIR`.
В development-режиме те же файлы лежат в `<проект>\data\`.

### Ограничения и безопасность

- OAuth-клиент в exe хранится как base64-блок, а не XOR-«шифрование»:
  это кодирование, а не защита. Цель — не дать прочитать
  `credentials.json` в Блокноте; извлечь config из exe технически можно
  (это свойство любого installed-app OAuth-клиента). Если требуется
  настоящая защита секрета — не встраивайте его: положите
  `credentials.json` в `%LOCALAPPDATA%\GoogleClassHelp\` (или укажите
  `GC_DASHBOARD_CREDENTIALS`) при первом запуске, как это делают
  `gcloud` и `gh`.
- Токен каждого пользователя живёт только в `%LOCALAPPDATA%`, в exe не
  зашивается и через фронтенд не отдаётся.
- Бэкенд слушает только `127.0.0.1`.

#### Security model

- сервер слушает только `127.0.0.1`; запросы с чужим `Host` или `Origin`
  отклоняются middleware (DNS-rebinding / чужие веб-страницы);
- CORS сам по себе не защищает от не-браузерных клиентов: ограничение —
  именно локальный bind плюс Host/Origin-guard, а не CORS;
- любой локальный процесс пользователя может вызывать API (чтение кэша и
  запуск синхронизации) — приложение не защищает машину от своего же
  пользователя и на это не претендует;
- все OAuth-scopes — read-only; приложение никогда ничего не изменяет в
  Google Classroom.

### Windows-интеграция (опционально, не автоматизировано)

Ярлык в Пуск/на рабочий стол создаётся вручную из
`release\GoogleClassHelp.exe`; автозапуск и установщик намеренно не
настраиваются без отдельного запроса.
#   g o o g l e - c l a s s - h e l p 
 
