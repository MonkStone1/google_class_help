# Этап 10 — Testing and Deployment: результат

Реализация этапа 10 миграции на хостинг
(`docs/migration/Testing and Deployment Part 1–4 num in query 10.md`,
§52–§88) вместе с
`docs/prompt/GoogleClassHelp_DDoS_Security_Code_Changes.md` как дополнением
по защите от абьюза. Опорные документы: аудит
`HOSTING_MIGRATION_AUDIT.md`, результаты этапов 2–9
(`HOSTING_MIGRATION_STAGE2.md`–`HOSTING_MIGRATION_STAGE9.md`), решение
`docs/adr/adr-0028-docker-caddy-cloudflare-deployment.md`.

Дата: 2026-09-24. Целевой хост: **1 vCPU / 1 GB**, домен
`classroomhelp.pp.ua`, Cloudflare Free + Tunnel.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §52 | Тесты auth / isolation / credentials / sync / teacher / DB | новый `tests/test_stage10_part1.py` (40 тестов) + существующие наборы этапов 2–9; матрица ниже (§2) |
| §53 | Fake Classroom-слой, `user_a/user_b`, общий `course_shared_id` | фикстуры-хелперы `_make_user/_add_session/_seed_course/_seed_work`; ключевой тест «один Google-id независимо у двух пользователей»; реальные Google-эндпоинты не вызываются |
| §54 | Dockerfile, compose, Caddyfile, `.env.example` | `Dockerfile` (multi-stage, non-root), `compose.yml` (5 сервисов), `Caddyfile`, `.dockerignore`; `.env.example` дополнен |
| §54 | Отдельный worker-контейнер | сервис `worker` (`python sync_worker.py`, ADR-0023) |
| §54 | Postgres не в интернет, web во внутренней сети | у `postgres` только `expose: 5432`, у `web` `expose: 8000`, у `caddy` `expose: 80`; наружу не публикуется ничего |
| §55 | Сеть БД `caddy → web`, `web/worker → postgres` | одна приватная network `internal`; никаких `ports:` у postgres/web |
| §56 | Persistence (volume), не эфемерные слои | именованные volumes `pgdata`, `appdata`, `caddy_data`, `caddy_config` |
| §57 | Бэкапы и восстановление | `tools/backup_postgres.sh` (`pg_dump -Fc`, rolling retention, restore + `alembic upgrade head`), раздел в README и чек-листе; `.env` бэкапится отдельно |
| §58 | `/api/health` + `/api/ready` без секретов | `ready` добавлен в `main.py`, без сессии, `SELECT 1`, 200/503; тесты на live/сломанную БД и отсутствие утечек |
| §72 | Container security | non-root `app`, slim-база, только pinned runtime-зависимости, нет shell-мусора, `.dockerignore`; секретов в слоях нет |
| §73 | Пин зависимостей без апгрейда всего | `backend/requirements-prod.txt` (точные версии) для образа; `requirements.txt` остаётся диапазонным для разработки; `npm ci` по lockfile; образы `postgres:16-alpine`, `caddy:2-alpine` |
| §77 | Локальные/dev-данные не в прод | `.dockerignore` + `.gitignore`; `data/`, `credentials.json`, `embedded_secrets.py`, `*.db`, `dist/`, `node_modules` исключены |
| §78 | Гигиена репозитория | `.gitignore`: явный `!.env.example`, `backups/`, `*.dump`; `git grep` по секретам чист (см. §6) |
| §79 | README + deployment docs | раздел «Развёртывание на хостинге» в README (два режима, env, OAuth-клиенты, callback, compose, бэкапы, тесты) + `docs/DEPLOYMENT_CHECKLIST.md` |
| §80 | ADR про деплой | `ADR-0028` (+ таблица соответствия остальным 7 пунктам §80); зарегистрирован в `docs/adr/README.md` |
| §81 | Порядок изменений | соблюдён: Docker начат только после 1–9; зафиксировано в ADR-0028 §1 |
| §82 | Acceptance-критерии | чек-лист приёмки на VPS в `docs/DEPLOYMENT_CHECKLIST.md` §5 + таблица ниже (§5); живой VPS-прогон остаётся за деплоем |
| §83 | What not to do | негативный чек в §5; автоматизируемые запреты уже закрыты кодом (wildcard CORS, `create_all` вне SQLite, токены вне браузера) |
| §84 | Финальная форма репозитория | структура сохранена без churn (плоский `backend/`, миграции `0001–0003`, `docs/adr`, `tests`); новые файлы деплоя в корне |
| §85 | Deliverables (12 пунктов) | код, миграции, compose, Caddyfile, `.env.example`, тесты, README, ADR, чек-лист — см. §4 |
| §86 | Final review pass (grep-аудит) | прогон по списку `TOKEN_FILE/client_secret/refresh_token/access_token/allow_origins/create_all/SyncState/_profile_cache/_login_state/127.0.0.1/localStorage` — классификация в §6 |
| §87 | Инварианты | проверяющее ядро перенесено в §7 без изменений смысла |
| DDoS §7 | `CF-Connecting-IP` | `proxy.client_ip()`: CF-заголовок только от доверенного пира, fallback на TCP-пир; 3 теста |
| DDoS §8/§11 | Лимиты | существующие бакеты этапа 9 + прод-значения консервативнее (логин 10/мин, синк 10/мин); cooldown per-user; не добавлен второй лимитер |
| DDoS §9 | Queued sync | `POST /api/sync` в hosted: 409 (уже идёт) / 429 (cooldown) / `queued` + `sync_requested`; работу делает воркер; desktop сохраняет inline |
| DDoS §10 | Ограничение воркеров под 1 vCPU | прод-профиль 2×1 = 2 потока, интервал 30 мин, stagger 600 с |
| DDoS §13 | Лимит размера запроса | `request_body max_size 2MB` в `Caddyfile` |
| DDoS §22/§23 | Non-root, секреты не в image | Dockerfile `USER app`; нет `COPY .env`/`ENV SECRET` |
| DDoS §24 | Health/ready | `/api/health` + `/api/ready`, без env/credentials в ответе |
| DDoS §25 | Мониторинг без платной платформы | `docker stats/ps/logs` + существующие `metrics.py`/`RequestStats`; пороги апгрейда в ADR-0028 §2.2 |
| DDoS §26 | Бэкапы | `tools/backup_postgres.sh`, дампы не в Git |
| DDoS §27–§29 | Тесты лимитов/изоляции/токенов | новый набор (429/409/queued, изоляция A/B, `invalid_grant` затрагивает только A) |
| DDoS §17 | Turnstile | **реализован env-gated**: `TURNSTILE_SITE_KEY/SECRET_KEY` (пустые = выкл), `GET /api/auth/turnstile`, `POST /api/auth/login/start` → siteverify fail-closed, `GET /api/auth/login` → `/?challenge=required` вместо обхода, виджет на `SignIn`, CSP только с включённым ключом, login-бакет + `metrics` |
| DDoS §18–§20 | Cloudflare edge | порядок и настройки в `DEPLOYMENT_CHECKLIST.md` §1 (Tunnel, managed DDoS, отсутствие лишних DNS) |
| DDoS §K | Порядок выкладки | `docs/DEPLOYMENT_CHECKLIST.md` повторяет §K с конкретными командами |
| §88 | Load test | `tools/load_test.py` (stdlib, p50/p95/p99, 5xx-порог) + раздел §8 чек-листа с acceptance-критериями; локальный смоук прогнан (см. §8) |
| §36/§48 | HSTS | `GC_DASHBOARD_HSTS_MAX_AGE=31536000` в `.env.example` (заголовок уходит только по https; при edge-HSTS — 0) |

## 2. Матрица §52 → тест

Всего тестов в проекте: **237 backend** (было 197) + **51 frontend**.
Новые: `tests/test_stage10_part1.py` — 40.

### Authentication (§52)

| Требование | Тест |
| --- | --- |
| unauth → 401 | `test_hosted_data_routes_require_a_session` (6 путей), `test_hosted_sync_route_requires_a_session` |
| valid session → current user | `test_valid_session_resolves_the_current_user` |
| expired session → 401 | `test_expired_session_is_rejected` |
| revoked session → 401 | `test_revoked_session_is_rejected` |
| logout invalidiрует сессию | `tests/test_hosted_auth.py::test_logout_revokes_the_session_but_keeps_the_google_grant` |
| OAuth state mismatch | `test_callback_without_state_is_rejected` + этап 2 |
| replay callback | этап 2 (`state одноразовый`) |
| две login-транзакции не мешают | `test_two_login_attempts_do_not_interfere` |

### User isolation (§52/§53)

| Требование | Тест |
| --- | --- |
| один provider-id независимо у двух | `test_same_google_course_id_lives_independently_for_two_users` |
| A не читает курсы/coursework B | `test_user_a_cannot_read_b_coursework_or_grades` |
| A не читает оценки B | там же (+ этап 4 IDOR-набор) |
| A не читает teacher roster B | `test_user_a_cannot_read_b_teacher_roster` |
| A не чистит кэш B | `test_user_a_cannot_clear_b_cache` |
| A не трогает sync B | `test_user_a_sync_does_not_touch_b_state` |

### Credentials (§52, DDoS §29)

| Требование | Тест |
| --- | --- |
| токен никогда не во фронт-ответе | `test_token_material_never_appears_in_responses` |
| B не получает креды A | `test_one_user_has_no_credentials_when_the_other_does` |
| refresh scoped | `test_invalid_grant_refresh_is_confined_to_its_owner` |
| invalid refresh бьёт только одного | тот же + `test_deleting_one_grant_leaves_the_other_user_alone` |

### Sync (§52, DDoS §9/§10)

| Требование | Тест |
| --- | --- |
| два пользователя синкаются параллельно | `test_two_users_have_independent_sync_locks` |
| у пользователя максимум один активный синк | `test_one_user_has_at_most_one_active_sync` |
| ручной и плановый не дублируются | `test_queue_flag_and_claim_helpers_exist` + этап 5 (`claim_sync`) |
| падение одного не останавливает других | `test_user_a_sync_does_not_touch_b_state` + этап 5 |
| queued-контракт ручки | `test_manual_sync_cooldown_expires`, `test_cooldown_is_per_user`, `test_user_a_sync_does_not_touch_b_state` (§queued) + этап 9 |

### Teacher mode (§52)

| Требование | Тест |
| --- | --- |
| teacher-курс остаётся teacher | `test_teacher_course_stays_teacher_and_student_course_stays_student` |
| тот же Google-юзер студент в другом курсе | там же |
| teacher-only endpoints отклоняют студенческий курс | `test_teacher_only_endpoints_reject_a_student_course` |
| студент не читает teacher-данные другого | `test_student_cannot_read_another_users_teacher_data` |

### Database (§52)

| Требование | Тест |
| --- | --- |
| миграции с чистой БД | `tests/test_user_scoped_schema.py`, `alembic check` (§8) |
| старт на текущей схеме | `test_core_tables_exist` + весь набор |
| FK и каскады | `test_deleting_a_user_cascades_their_cache` + этап 3 |
| конкурентная безопасность | этап 5 (`claim_sync`), `test_one_user_has_at_most_one_active_sync` |
| поведение пула соединений | `test_connection_pool_is_released_between_requests` |

### Health / readiness (§58, DDoS §24) и client IP (DDoS §7)

`test_health_endpoint_is_public_and_minimal`,
`test_ready_endpoint_reports_database_up`,
`test_ready_endpoint_reports_503_when_the_database_is_down`,
`test_ready_endpoint_is_public_without_a_session`,
`test_ready_endpoint_never_leaks_infrastructure_details`,
`test_cf_connecting_ip_*` (3 теста).

## 3. Файлы

Добавлено:

- `tests/test_stage10_part1.py` — 40 тестов этапа 10;
- `tests/test_stage10_turnstile.py` — 11 тестов Turnstile (DDoS §17);
- `tools/load_test.py` — HTTP load-test (§88, только stdlib);
- `Dockerfile`, `compose.yml`, `Caddyfile`, `.dockerignore`;
- `backend/requirements-prod.txt` — пины рантайма для образа;
- `tools/backup_postgres.sh` — backup/restore;
- `docs/adr/adr-0028-docker-caddy-cloudflare-deployment.md`;
- `docs/DEPLOYMENT_CHECKLIST.md`;
- `docs/migration/audits/HOSTING_MIGRATION_STAGE10.md` (этот файл).

Изменено:

- `backend/main.py` — `GET /api/ready`, guard allow-list, импорты
  `Depends`/`select`/`Session`/`get_db`/`SQLAlchemyError`;
- `backend/api.py` — queued-ветка `POST /api/sync` (импорт `timezone`),
  `SyncResult(ok, queued, status)`;
- `backend/schemas.py` — поля `queued`/`status` в `SyncResult`;
- `backend/sync.py` — реэкспорт `request_sync`;
- `backend/proxy.py` — `CF-Connecting-IP` только от доверенного прокси;
- `frontend/src/context/DataContext.tsx` — ожидание фонового завершения
  queued-синка (опрос `/api/status`, спиннер);
- `frontend/openapi.json`, `frontend/src/api-schema.d.ts` — перегенерированы;
- `tests/test_api_auth.py`, `tests/test_sync_volume.py`,
  `tests/test_user_isolation.py`, `tests/test_stage9_limits_capacity.py` —
  под новый контракт;
- `.env.example` — прод-значения 1/1, секция Container deployment
  (`POSTGRES_*`, `CLOUDFLARE_TUNNEL_TOKEN`, `BACKUP_*`);
- `.gitignore`, `README.md`, `docs/adr/README.md`.

## 4. Deliverables §85

| # | Артефакт | Где |
| --- | --- | --- |
| 1 | Код | `backend/` (queued sync, ready, CF-IP) |
| 2 | Миграции | `migrations/versions/0001–0003` |
| 3 | Compose | `compose.yml` |
| 4 | Caddyfile | `Caddyfile` |
| 5 | `.env.example` | корень |
| 6–8 | Тесты (security/isolation/OAuth) | `tests/` (237 backend, 51 frontend) |
| 9 | README | `README.md` |
| 10 | ADR | `docs/adr/adr-0028-*` + ADR-0020…0027 |
| 11 | Аудит | этот файл |
| 12 | Deployment checklist | `docs/DEPLOYMENT_CHECKLIST.md` |


## 5. Приёмка (§82) и негативный чек (§83)

Что доказывается автоматически (уже прогнано):

- изоляция пользователей, токены, teacher-гейты, sync-локи, БД-каскады,
  health/ready — тестами выше;
- запрет wildcard CORS: `config._normalize_origins` отбрасывает `*` при
  credentials (тесты этапа 7);
- `create_all` только для SQLite, PostgreSQL — Alembic (тесты этапа 3);
- токенов нет в `localStorage`/`sessionStorage`/статусе — `git grep` пуст
  по `access_token|refresh_token|client_secret`, а `localStorage` встречается
  только в UI-настройках (ADR-0006);
- hosted не тянет desktop-модули (подпроцесс-тест этапа 8);
- секретов нет в отслеживаемых файлах (§6).

Что доказывается только на живом стенде (чек-лист, `DEPLOYMENT_CHECKLIST.md`
§5, за владельцем деплоя):

- `docker compose up` на VPS, все сервисы healthy;
- первый `alembic upgrade head` на живой PostgreSQL (отложен с этапов 3/5/9);
- два реальных Google-аккаунта не видят данные друг друга;
- Postgres/8000 недоступны снаружи (`nc -vz` отказ);
- HTTPS-сертификат, `curl /api/health` и `/api/ready`;
- queued-синк в UI (спиннер сразу после `queued`, затем terminal status и
  автоматическое обновление данных; 409/429 на повторные клики);
- backup→restore на тестовой БД.

Сознательно НЕ делалось (§83):

- не подняли платный WAF/Redis/Celery/Kubernetes/второй VPS;
- не вынесли лимитер в Redis (одна web-реплика — задокументированное
  ограничение ADR-0028 §4);
- не публиковали порты origin и не создавали DNS-имена, светящие IP VPS;
- не меняли grading-правила и read-only scopes;
- Turnstile включён не по умолчанию (нужны ключи в env — это выключатель,
  а не отложенная задача); HSTS включён в `.env.example`.

## 6. §86 — grep-аудит (по отслеживаемым файлам)

| Паттерн | Найдено | Классификация |
| --- | --- | --- |
| `TOKEN_FILE` | `backend/auth.py`, `backend/config.py` | desktop-only (`token.json`), hosted-путь его не читает (этап 4) |
| `_login_state` | `backend/auth.py` | desktop-only loopback-флоу (ADR-0019); hosted использует `oauth_login_states` |
| `_profile_cache` | `backend/api.py` | user-scoped кэш: ключ `user.id` (этап 4/§17) |
| `SyncState` | нет в backend/tests (только downgrade миграции 0002) | заменён на `sync_status` (этап 5) |
| `create_all` | `backend/database.py` (SQLite-ветка), docstring | PostgreSQL-путь идёт через Alembic (этап 3) |
| `allow_origins` | `backend/main.py:303` | `list(CORS_ORIGINS)`, wildcard запрещён конфигом |
| `localStorage` | `frontend/src/context/SettingsContext.tsx`, `lib/assignmentFilters.ts` | только UI-настройки (ADR-0006); токенов нет |
| `sessionStorage` | нет | — |
| `client_secret` / `refresh_token` / `access_token` | нет в коде/тестах | только имена env-переменных в комментариях/доках |
| `127.0.0.1` / `localhost` | нет в backend/frontend/tests | dev-дефолты приходят из конфигурации через env; тесты параметризуют Host/CORS |
| `backend/embedded_secrets.py`, `credentials.json`, `data/token.json` | git-ignored, в истории отсутствуют | desktop-клиент, hosted-контур их не использует (аудит этапа 2) |

## 7. §87 — инварианты (рамка ревью)

```text
сессия браузера → один application-user → один Google-credential-set
   → один user-scoped кэш → его per-user sync-jobs → все запросы скоуплены
teacher — роль per-course (ADR-0017), не флаг аккаунта
Google — авторитет, PostgreSQL — кэш, браузер — только safe-данные,
секреты — только сервер (env), origin скрыт за Cloudflare Tunnel
```

Любая неоднозначность решалась в пользу простейшего безопасного варианта и
записывалась в ADR-0028 (queued-синк, CF-IP, 1/1-профиль, env-gated
Turnstile, включённый HSTS). Спекулятивная инфраструктура не добавлялась.

## 8. Проверки

- `pytest -q`: **248 passed** (было 197; +40 §52/§53, +11 Turnstile).
- `ruff check` / `ruff format --check` (backend, tests, migrations,
  `tools/load_test.py`): чисто.
- `npx pyright` (`pyrightconfig.json`): **0 errors, 0 warnings**.
- `npm run lint` (eslint + `tsc --noEmit`): чисто.
- `npx vitest run`: **51 passed** (7 файлов).
- `docker compose config --quiet` с временным `.env`: **OK** (5 сервисов,
  все пути/переменные подставляются).
- **Load-test смоук (§88):** `tools/load_test.py` против живого dev-сервера
  (uvicorn, SQLite, `/api/health` + `/api/ready`): 300 запросов @ 10 →
  **PASS**, 300/300 OK, ~220 req/s, p50 22.5 ms, p95 43.6 ms, 0 5xx,
  exit code 0. Против прод-стенда — §8 чек-листа.
- `git grep`-аудит §86: чисто по секретам (см. §6).
- Alembic: миграции `0001–0003` не менялись в этом этапе; прогон
  `alembic upgrade head`/`check` на живом PostgreSQL — в чек-листе (нет
  сервера в среде разработки, как и на этапах 3/5/9).
- Ограничения среды: `Caddyfile` и `tools/backup_postgres.sh` прогнаны
  только синтаксически/через `docker compose config` — фактический запуск
  Caddy/cloudflared и `pg_dump` происходит на VPS при выкате; реальный
  Turnstile siteverify требует ключей Cloudflare (покрыт моками).
- Секретов в отслеживаемых исходниках нет; новых env-переменных — только
  плейсхолдеры в `.env.example`; временный `.env` после проверки удалён.

## 9. Что осталось за пределами этапа 10

- **Живой деплой на VPS** по `docs/DEPLOYMENT_CHECKLIST.md`: первый
  `alembic upgrade head` на PostgreSQL, smoke двух аккаунтов, проверка
  закрытых портов, backup/restore.
- **Load-test на прод-стенде** — §8 чек-листа (критерии §88 в
  ADR-0027 §7 / ADR-0028 §2.2); сам инструмент готов и локально прогнан.
- **Turnstile на проде** — заполнить ключи в `.env` (код готов, дефолт
  выключен); **HSTS** уже включён в `.env.example`.
- **Смоук собранного exe** (desktop): `build.bat` не менялся, desktop-код
  этапа 10 не затронут (изменения только в hosted-ветках и общих хелперах,
  покрытых тестами).
- **Gitleaks в CI** — CLI в этой среде отсутствует; в пайплайне деплоя.

