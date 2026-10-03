# Local Google Classroom Dashboard

Локальный дашборд Google Classroom: FastAPI + SQLite-кэш на бэкенде,
React (Vite) на фронтенде. Работает только на localhost, данные синхронизируются
с Google Classroom API (read-only scopes, см. `docs/adr/adr-0002`).

Два режима работы: **разработка** (два процесса: uvicorn + Vite dev-сервер)
и **production** (один exe-файл `GoogleClassHelp.exe` на Nuitka).

---

## FEEDBACK (тикеты обратной связи, ADR-0035)

Авторизованный пользователь открывает **Feedback** в боковом меню и выбирает
одно из двух: **Create a ticket** (создать) или **My tickets** (свои
обращения). Тикет — это категория (`bug` / `problem` / `suggestion` /
`other`), тема, Markdown-сообщение и **необязательные** вложения.

- **Имя и почту вводить не нужно**: личность берётся из сессии, а профиль
  обновляется из Google при каждом входе.
- Ответ поддержки приходит в тот же тикет; ответ на **решённый** тикет
  открывает его снова (`in_progress`) — см. ADR-0035.
- Markdown хранится как есть и **рендерится с санитизацией**
  (`rehype-sanitize`); сырой HTML не вставляется нигде.

Администрирование вынесено в отдельную консоль **`/admin`** (ADR-0036): пункт меню в общем сайте убран, единственный вход — URL `https://classroomhelp.pp.ua/admin`. В консоли: сводка, все тикеты с фильтрами и поиском, любой тикет, смена статуса, удаление и — у Super Admin — раздел **Administrators** (e-mail, имя, дата, удаление).

- **Роли решает бэкенд** по e-mail текущей сессии. Фронтенд получает два булевых флага (`is_admin`, `is_super_admin`) и ничего больше; ни один флаг не лежит в браузере, и ни один запрос не может повысить роль.
- **Обычные администраторы** — строки таблицы `admins` в PostgreSQL. Заводит и удаляет их **только Super Admin** через `/admin/admins`. Больше они не могут ничего: работа с тикетами и статистика общие для обеих ролей.
- **Super Admin** настраивается исключительно переменной `SUPER_ADMIN_EMAIL`, только на сервере. Это не строка реестра, поэтому его нельзя удалить через UI или API. Не задана — значит Super Admin нет (fail closed).
- **`ADMIN_EMAILS` больше не существует** и нигде ничего не разрешает. Бывших администраторов нужно один раз завести заново через `/admin/admins` (см. `docs/DEPLOYMENT_CHECKLIST.md`).
- Неадминистратор на `/admin` получает перенаправление на `/`, обычный администратор на `/admin/admins` — на `/admin`. Это только UX: `require_admin` и `require_super_admin` на бэкенде отвечают 403 в любом случае.

Переменные окружения (все — в `.env`, см. `.env.example`):

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `SUPER_ADMIN_EMAIL` | *(пусто)* | единственный Super Admin; пусто ⇒ суперадмина нет |
| `GC_DASHBOARD_FEEDBACK_TICKETS_PER_HOUR` | `5` | новых тикетов на пользователя в час |
| `GC_DASHBOARD_FEEDBACK_REPLIES_PER_HOUR` | `30` | ответов на пользователя в час |
| `GC_DASHBOARD_FEEDBACK_MAX_SUBJECT_CHARS` | `200` | длина темы |
| `GC_DASHBOARD_FEEDBACK_MAX_MESSAGE_CHARS` | `20000` | длина сообщения |
| `GC_DASHBOARD_FEEDBACK_MAX_ATTACHMENTS` | `3` | файлов на сообщение |
| `GC_DASHBOARD_FEEDBACK_MAX_ATTACHMENT_BYTES` | `5242880` | байт на файл (5 МБ) |
| `GC_DASHBOARD_FEEDBACK_MAX_TOTAL_BYTES` | `10485760` | байт на сообщение (10 МБ) |
| `GC_DASHBOARD_RATE_LIMIT_FEEDBACK_PER_MINUTE` | `30` | грубый per-IP предел на POST тикетов |

Вложения: только `jpg`, `png`, `gif`, `pdf`, `txt`, определяются **по
содержимому** (не по расширению и не по `Content-Type` клиента), хранятся на
томе `appdata` под серверным именем и раздаются авторизованным endpoint'ом.
Из-за этого `Caddyfile` поднимает `request_body max_size` с 2MB до 16MB.

Удаление тикета **окончательное** (каскад по БД + снятие файлов) и всегда
подтверждается диалогом во фронтенде.

---

## ПОДДЕРЖКА ПРОЕКТА (QR-коды, ADR-0037)

Сайт бесплатный, поэтому его можно поддержать. Блок с QR-кодами двух банков
рендерится компонентом
`frontend/src/components/DonateCards.tsx` и показывается в **настройках**
(`/settings`, между «Внешний вид» и «Локальные данные») — карточка **свёрнута по
умолчанию** и открывается кнопкой «Поддержать проект». Поддержка — не
настройка, и развёрнутый блок отодвинул бы вниз «Локальные данные», за которыми
чаще всего и приходят в эту страницу.

На **публичном лендинге** (`/`) блока нет: страница нужна, чтобы объяснить, что
это за сайт, и провести гостя через вход через Google, а просьба о деньгах
посреди этого потока прерывает единственное действие, ради которого страница
существует, и обращается к человеку, который ещё не видел продукт в работе
(ADR-0038).

Под каждым кодом сказано, что деньги пойдут на поддержание и развитие
проекта. Текст лежит в словарях `en`/`ru`/`uk` (`donate.note`), поэтому
страница следует языку интерфейса, а `tsc` падает при забытом переводе.

Фраза стоит **по центру сверху**, коды расходятся **по краям**. Название банка
под карточкой не дублируется: оно уже нарисовано в самой картинке, для
доступности оно живёт в `aria-label` кнопки.

**Клик по коду открывает его увеличенным** — в размере, при котором два кода
помещаются на страницу, камера телефона на вытянутой руке код не читает.
Диалог закрывается по Escape, клику по фону и кнопке, а фокус возвращается на
код (он же доступен с клавиатуры — это кнопка, а не картинка).

### Картинки

```
frontend/public/donate/monobank.png     1051×1280
frontend/public/donate/privatbank.png   1056×1280
```

`frontend/public/` копируется Vite в `frontend/dist` дословно, а `dist`
попадает и в Docker-образ, и в одноразовый exe (`build.bat`) — править
`build.bat` не нужно. Оба файла с расширением `.png` фактически являются
JPEG; браузеры это принимают, переименовывать не нужно.

**QR нельзя перекрашивать и нельзя растягивать.** У кодов свой фон, поэтому у
`.donate-qr` нет ни белой подложки, ни `filter`, ни `mix-blend-mode` — тему
несёт рамка `.donate-card` вокруг картинки. Размеры тоже заданы по факту:
ограничен только `width`, а `height: auto`, потому что картинки вертикальные
и разного размера; жёсткий квадрат растянул бы код так, что банковское
приложение его перестаёт читать.

**При замене картинки** на файл другого размера поправьте `width`/`height` в
`BANKS` (`frontend/src/components/DonateCards.tsx`) — тест
`tests/test_stage8_coexistence.py` упадёт и сам подскажет фактический размер.

Картинки same-origin, поэтому работают без правок CSP (`img-src 'self' data:`,
ADR-0026 §48). В одноразовом exe блок тоже показывается — это осознанное решение
(ADR-0037).

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

### Структура `backend/`

`backend/` — корень `sys.path`, поэтому всё, что лежит в нём **напрямую**,
видно всему процессу вместе с `site-packages`. Домен разложен по слоям-пакетам
(ADR-0039):

```text
core/  ←  db/  ←  gapi/  ←  sync/  ←  api/routes  ←  main.py
                     ↖  auth/  ↖  feedback/
```

Плоско в корне осталось только то, что привязано сборкой: `main.py`,
`launcher.py`, `path_config.py`, `maintenance.py`, `build_secrets.py`,
`embedded_secrets.py` (ADR-0016).

Каталог `google/` **нельзя** вернуть: он затенил бы установленные `google-auth`,
`google-api-python-client` и `google-auth-httplib2`. Отсюда `gapi/`.

Полная карта, правила импортов и бюджеты строк — в
[`docs/BACKEND_STRUCTURE.md`](docs/BACKEND_STRUCTURE.md). Автоматически
проверяются `tests/test_backend_structure.py` и `ruff.toml`.

### Структура `frontend/`

`frontend/src/` разделён на шесть слоёв (ADR-0040). Разрешённая стрелка
импортов — одна, справа налево:

```text
shared/  ←  entities/  ←  features/  ←  widgets/  ←  pages/  ←  app/
```

| Слой | Что в нём |
|---|---|
| `shared/` | `api/` (транспорт + эндпоинты + генерируемый `schema.d.ts`), `hooks/`, `lib/` (только чистые функции), `i18n/`, `types/`, `config/`, `test/`, `ui/` |
| `entities/` | `assignment/`, `course/`, `grades/`, `feedback/`, `user/` — доменные типы и правила отображения, без `fetch` |
| `features/` | `assignments-filter/`, `assignment-modal/`, `global-search/`, `notifications/`, `sync/`, `donate/`, `feedback-ticket/` |
| `widgets/` | `sidebar/`, `topbar/`, `landing/`, `markdown/` — крупные блоки оболочки |
| `pages/` | маршрут = папка `{ui/, model/, page.css}` |
| `app/` | `router/`, `layouts/`, `providers/`, `boot/`, `toaster/`, `styles/`, `main.tsx` — импортируется **только** из `app/main.tsx` |

Наружу у каждой папки-слайса торчит только её `index.ts`: импорт вроде
`from "../../entities/feedback/status.ts"` запрещён. `shared/lib/` не содержит
импорта `react` вовсе, а `entities/` не знает про `api.*` и `react-router-dom`.

Полная карта, бюджеты строк, порядок CSS и рецепт добавления фичи —
[`docs/FRONTEND_STRUCTURE.md`](docs/FRONTEND_STRUCTURE.md). Проверяют всё это
`frontend/src/test/structure.test.ts` и `eslint.config.js`
(`no-restricted-imports`), обе проверки — в обычном `npm test` / `npm run lint`.

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

### Локальный Docker с Google OAuth

Локальный hosted-стенд запускает тот же Docker image, что и production, но
без Caddy и Cloudflare. Браузер обращается к `http://127.0.0.1:8000`, а
PostgreSQL, web и worker общаются по отдельной Docker-сети. Это позволяет
проверить настоящий Google OAuth, сессии, шифрование токенов, Alembic и
синхронизацию Classroom, не используя production-домен или tunnel-токен.

#### Настройка Google Cloud

1. В **API & Services → Library** включите **Google Classroom API**.
2. Настройте OAuth consent screen/Audience как **External → Testing** и
   добавьте свой Google-аккаунт в **Test users**. Полная verification для
   локального тестового пользователя не нужна.
3. Создайте **отдельный OAuth client типа Web application**. Не используйте
   desktop-клиент из `backend/credentials.json`: hosted-режим берёт web
   client ID/secret только из environment.
4. В качестве Authorized redirect URI укажите ровно:

   ```text
   http://127.0.0.1:8000/api/auth/callback
   ```

   Google разрешает HTTP для loopback IP у web-приложения. Не используйте
   `localhost` в этом URI: адрес и порт должны точно совпадать с тем, что
   отправляет приложение. Сайт также открывайте по `127.0.0.1`, иначе
   OAuth-cookie и callback будут привязаны к другому hostname.

Приложение запрашивает OIDC scopes `openid`, `profile`, `email` для
идентификации профиля и четыре read-only Classroom scope:
`classroom.courses.readonly`, `classroom.student-submissions.me.readonly`,
`classroom.student-submissions.students.readonly` и
`classroom.rosters.readonly`. Оно никогда не изменяет данные Classroom.

#### Подготовка environment

Из корня проекта:

```bat
cd D:\Documents\google_class_help
Copy-Item .env.local.example .env.local
```

Откройте `.env.local` и заполните `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET` и `POSTGRES_PASSWORD`. Затем сгенерируйте ключ:

```bat
.venv\Scripts\python.exe tools\generate_hosted_secrets.py
```

Скопируйте выведенное значение `GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY` в
`.env.local`. Не перезаписывайте этот ключ при обычных перезапусках: он нужен
для расшифровки уже сохранённых OAuth-токенов. Файл `.env.local` игнорируется
Git и не попадает в Docker image.

Локальный `compose.local.yml` сам включает `GC_DASHBOARD_HOSTED=1`,
`APP_ENV=development`, PostgreSQL и отдельный worker. Он намеренно не включает
Caddy/Cloudflare, production `.env`, HSTS и Secure-cookie: Google OAuth здесь
использует разрешённый loopback HTTP callback.

#### Сборка и запуск

Во всех командах нужен один и тот же `--env-file`: Compose использует его и
для подстановки пароля PostgreSQL, и для переменных контейнеров.

```bat
docker compose --env-file .env.local -f compose.local.yml config --quiet
docker compose --env-file .env.local -f compose.local.yml build web
docker compose --env-file .env.local -f compose.local.yml up -d postgres
docker compose --env-file .env.local -f compose.local.yml run --rm --workdir /app web alembic -c /app/alembic.ini upgrade head
docker compose --env-file .env.local -f compose.local.yml up -d web worker
```

Откройте <http://127.0.0.1:8000> и войдите через Google. После callback
worker автоматически выполнит первый запрос синхронизации (в локальном
compose уменьшены задержки сканирования). Проверить состояние контейнеров и
логи можно командами:

```bat
docker compose --env-file .env.local -f compose.local.yml ps
docker compose --env-file .env.local -f compose.local.yml logs --tail=100 web worker
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/ready
```

Ожидаемые ответы health/ready: `ok = True`, а у `/api/ready` также
`db = up`. Если Google сообщает `redirect_uri_mismatch`, проверьте, что в
Google Cloud указан именно `http://127.0.0.1:8000/api/auth/callback`, а в
`compose.local.yml` задан тот же `GOOGLE_REDIRECT_URI`.

Остановить стенд, сохранив локальную БД и OAuth-токены:

```bat
docker compose --env-file .env.local -f compose.local.yml down
```

Полностью удалить **только локальные** volumes БД и данных приложения:

```bat
docker compose --env-file .env.local -f compose.local.yml down --volumes
```

Этот вариант не проверяет Caddy, Cloudflare, публичный HTTPS и HSTS —
для них нужен отдельный deployment-контур. Он проверяет локальный Docker и
реальный Google OAuth end-to-end.


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
  Без сессии корень `/` отдаёт посадочную страницу с описанием сервиса
  и входом через Google (ADR-0029); ссылка на `/privacy/` есть и в её
  футере, и в разделе о данных.
- Секреты: desktop-клиент встраивается в exe (base64 — обфускация, не
  защита); hosted-секрет (`GOOGLE_CLIENT_SECRET`, ключ Fernet) — только
  env сервера, никогда в браузере, `frontend/dist`, Nuitka-артефактах и Git.

### Rate limits, capacity и retention (миграция на хостинг, этап 9, ADR-0027)

- **Лимиты (только hosted):** токен-бакеты по (поверхность, client IP) —
  логин 30/мин, отклонённые OAuth-callback'и 20/мин, ручной синк 60/мин
  **плюс cooldown 60 с на пользователя**, очистка кэша 10/мин; превышение
  → 429 + `Retry-After`. IP из `CF-Connecting-IP`/`X-Forwarded-For`
  верится только от доверенного прокси. Desktop не лимитируется.
  Прод-`.env` для 2 vCPU / 2 GB ставит консервативнее: логин 10/мин, синк
  10/мин.
- **Бюджет синка:** `SYNC_MAX_WORKERS` × `SYNC_MAX_CONCURRENT_USERS`;
  на целевом VPS 2 vCPU / 2 GB это `2 × 1 = 2` потока, интервал 30 мин,
  стартовый stagger 600 с — очередь вместо залпа. Арифметика в
  `backend/core/capacity.py`; рост лимитов — только вместе со счётчиками
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
  (короткие транзакции на фазы); пул `3+2` соединений на 2 vCPU / 2 GB.

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

1. генерирует иконку приложения `assets/GoogleClassHelp.ico` и фавики
   сайта в `frontend/public` (`tools/make_icon.py`) — этот шаг идёт
   **первым**, потому что Vite копирует `frontend/public` в `frontend/dist`,
   и иконка должна существовать до `npm run build`;
2. чистит и пересобирает фронтенд: `npm run build` → `frontend/dist`;
3. встраивает OAuth-клиент: `backend/build_secrets.py` генерирует
   `backend/embedded_secrets.py` (XOR+base64 со случайным ключом) из
   `backend/credentials.json`;
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
   откроется лишняя вкладка: бэкенд при этом всё равно один — защиту
   держит мьютекс. Раньше вкладка пыталась вернуть фокус прежней, но на
   захощенном домене это уведомление было лишним, поэтому слой presence
   удалён (ADR-0029).
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
- Classroom OAuth-scopes — только read-only; OIDC scopes дают лишь профиль
  текущего Google-пользователя. Приложение никогда ничего не изменяет в
  Google Classroom.

### Windows-интеграция (опционально, не автоматизировано)

Ярлык в Пуск/на рабочий стол создаётся вручную из
`release\GoogleClassHelp.exe`; автозапуск и установщик намеренно не
настраиваются без отдельного запроса.
