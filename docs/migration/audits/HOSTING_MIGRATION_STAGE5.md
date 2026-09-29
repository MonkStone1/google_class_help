# Этап 5 — Multi-User Synchronization: per-user планировщик, `sync_status`, воркер

Реализация этапа 5 миграции на хостинг
(`docs/migration/Multi-User Synchronization num in query 5.md`, §18, §19, §20,
§63, §64). Опорные документы: аудит `HOSTING_MIGRATION_AUDIT.md`, результаты
этапов 2–4 (`HOSTING_MIGRATION_STAGE2.md`–`HOSTING_MIGRATION_STAGE4.md`),
решение `docs/adr/adr-0023-per-user-sync-scheduler.md`.

Дата: 2026-09-20. Все разделы промпта этапа 5 реализованы.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §18 | scheduler/worker: поиск должных пользователей → per-user джобы | `backend/sync_scheduler.py`: `select_due_users` → bounded pool → `sync_service.sync_user_id(user_id)`; `backend/sync_worker.py` — владелец расписания |
| §18 | не держать один глобальный лок на всех пользователей | `_SYNC_LOCK` удалён; per-user локи `_sync_lock_for(user_id)` — два аккаунта синкаются параллельно |
| §18 | синк одного пользователя не может запуститься дважды | per-user лок (один процесс) + условный UPDATE `sync_store.claim_sync` (несколько воркер-контейнеров); stale-claim перехватывается через `SYNC_CLAIM_STALE_SECONDS` |
| §18 | сломанный токен/403 одного не останавливает остальных | каждый джоб — своя сессия, свои креденшелы, свой try/except (`run_user`); ошибка пишется в `sync_status` этого пользователя (тест) |
| §18 | per-user состояние синка вместо глобального `SyncState(key,value)` | таблица `sync_status` (одна строка на пользователя): `status`, `last_started_at`, `last_finished_at`, `last_success_at`, `last_error`, `last_error_at`, `consecutive_failures`, `sync_requested`; Alembic-ревизия `0002` (drop `sync_state`) |
| §18 | не показывать фронтенду сырые трейсы и креденшелы | `sync_service._public_error`: только короткие фразы по HTTP-статусу; трейс остаётся в логе; `last_error` ≤ 500 символов, без текста исключения (тест с `SECRET`-строкой) |
| §19 | выбрать вариант прод-планировщика и задокументировать | Option A — отдельный воркер-контейнер (`sync_worker.py`); web-процесс не запускает расписание; opt-in `GC_DASHBOARD_EMBEDDED_SCHEDULER=1` для одной реплики; ADR-0023 |
| §19 | при нескольких репликах/воркерах не плодить дубли джоб | дедупликация в БД (`claim_sync`), а не в памяти процесса — встроенный режим тоже безопасен; Celery/Redis сознательно не добавлены |
| §20 | сохранить staged/parallel sync (ADR-0014) | пул, thread-local клиенты, backoff 429, зеркальная очистка — без изменений; добавлен только контекст пользователя (`sync_now(user)` / `sync_user_id(user_id)` вместо скрытого глобального пользователя) |
| §63 | синхронизировать только активных с валидным грантом | кандидаты: `is_active`, `provider="google"`, есть строка `oauth_tokens`, `status != needs_reauth` |
| §63 | при постоянной неудаче refresh — `needs_reauth` и пауза | `sync_now` различает «не входил» и «грант сломан» (`google_credentials.has_google_grant`); второй вариант ставит `needs_reauth`; планировщик такие аккаунты пропускает |
| §63 | избегать retry-штормов | backoff `интервал × 2^min(падений,3)` (до 8×); `consecutive_failures` обнуляется успехом |
| §63 | выход из паузы при повторном входе | `hosted_auth` после логина вызывает `sync_store.request_sync` → флаг `sync_requested` (снимает `needs_reauth`, делает аккаунт должным немедленно) |
| §64 | не синхать все аккаунты в один момент после деплоя | детерминированный per-user оффсет (`SHA-256("gch-sync-<id>")`, не солёный `hash()`); первый запуск — в окне `min(интервал, SYNC_STARTUP_STAGGER_SECONDS)` от `created_at`; батч скана = число свободных слотов → очередь, а не залп |
| §64 | сохранить свежесть без startup-шторма | скан каждые `SYNC_SCAN_INTERVAL_SECONDS` + случайный jitter между воркерами; `POST /api/sync` и `sync_requested` дают свежесть по требованию |

## 2. Файлы

Добавлено:

- `backend/sync_scheduler.py` — per-user планировщик: выбор должных
  (§63), stagger/backoff (§63/§64), bounded очередь (`SyncScheduler`),
  блокирующий батч (`sync_users`) для `--once` и тестов; module-singleton
  `start()/stop()` для встроенного режима.
- `backend/sync_worker.py` — воркер-процесс (§19 Option A): цикл до
  SIGTERM/SIGINT (корректный `docker stop`) или `--once` для cron; тот же
  env, что у web-процесса (`DATABASE_URL`, ключ шифрования, web-клиент).
- `migrations/versions/0002_per_user_sync_status.py` — создание `sync_status`,
  удаление `sync_state`; downgrade восстанавливает `sync_state`.
- `tests/test_sync_scheduler.py` — 18 тестов.

Изменено:

- `backend/models.py` — `SyncState` → `SyncStatus` (структурированные поля,
  статус-машина, claim-семантика).
- `backend/sync_store.py` — слой sync-состояния: `claim_sync`,
  `mark_sync_succeeded/failed/needs_reauth/pending`, `request_sync`,
  `last_sync_time`, `last_sync_error`, `sync_status`; `reset_cache` удаляет
  строку `sync_status` владельца.
- `backend/sync_service.py` — `sync_now(user)`/`sync_user_id(user_id)`,
  per-user локи, claim перед сетевой работой, переходы состояния,
  санитизация ошибок; stage-логика ADR-0014 не тронута.
- `backend/google_credentials.py` — `has_google_grant(db, user)`: «есть ли
  грант» без чтения токенов (для различия «не входил»/«грант сломан»).
- `backend/hosted_auth.py` — после логина `sync_store.request_sync(user.id)`.
- `backend/config.py` — общий `_int_env`; `SYNC_MAX_CONCURRENT_USERS`,
  `SYNC_SCAN_INTERVAL_SECONDS`, `SYNC_STARTUP_STAGGER_SECONDS`,
  `SYNC_CLAIM_STALE_SECONDS`, `EMBEDDED_SCHEDULER`.
- `backend/main.py` — lifespan: hosted без встроенного планировщика по
  умолчанию; opt-in embedded-режим; desktop-цикл без изменений.
- `backend/background_sync.py` — docstring: остаётся desktop-расписанием,
  синк теперь под per-user локом.
- `backend/api.py`, `backend/schemas.py` — `/api/status` и detail-ручки
  читают `last_sync`/`last_sync_error` из `sync_status`; новые поля
  `sync_status`, `last_sync_started_at`, `last_sync_finished_at`;
  `syncing` теперь реальный признак «идёт синк»; docstring `/api/sync`
  обновлён (конфликт — только с синком того же пользователя).
- `backend/sync.py` — фасад: `get_state`/`get_state_datetime` →
  `sync_status`/`last_sync_time`/`last_sync_error`, константы статусов,
  `sync_user_id`.
- `backend/database.py` — `_import_models` регистрирует `SyncStatus`.
- `frontend/openapi.json`, `frontend/src/api-schema.d.ts` — перегенерированы
  (`tools/dump_openapi.py` + `npm run gen:api:file`); `tsc`/eslint проходят.
- `.env.example`, `ruff.toml` (isort first-party), `docs/adr/README.md`,
  `docs/CODE_REVIEW_BACKEND.md` (пример фасада).

## 3. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| Y1 | `_SYNC_LOCK` — один синк на процесс | per-user локи + claim в БД; параллельный синк разных аккаунтов (тест) |
| Y6 | `background_sync` — глобальное расписание на процесс | hosted: per-user scheduler/worker; desktop-цикл сохранён как есть |
| S3 | `lifespan` стартует глобальный цикл | hosted-веб не планирует ничего; opt-in embedded; воркер — отдельный процесс |
| A6 | после логина — один глобальный sync | после логина — request синка конкретного пользователя (`sync_requested`) |
| C4 | бюджет синка рассчитан на 1 пользователя | пер-юзерский интервал, `SYNC_MAX_CONCURRENT_USERS`, scan/stagger/claim-настройки (пересчёт квот — этап 9) |
| M4 | `SyncState` — key/value без структуры | `sync_status`: статус-машина, таймстемпы, счётчик падений, флаг запроса |
| — | `last_sync_error` = `f"{Class}: {exc}"` в API | санитизированные фразы, трейс только в логе (§18) |
| — | после логина hosted-синк не запускался | `sync_requested` сразу после сохранения гранта |

## 4. Тесты (93 всего, все зелёные; было 75)

Новые (`tests/test_sync_scheduler.py`):

- §18: синк того же пользователя под локом → `ALREADY_RUNNING`, другой
  пользователь идёт дальше; реестр локов ключуется по id;
- §18: крэш джобы не выпадает наружу; `_public_error` не содержит текст
  исключения (`refresh_token=abc`, `SECRET`-строка); 403 → фраза «denied
  access», прочее → generic;
- §18: неудачный синк пишет санитизированный `last_error`, инкремент
  `consecutive_failures`, `last_finished_at` — в строку владельца;
- §19: claim атомарен (второй воркер отказан), stale-claim перехватывается;
  нулевой stale-окно не «крадёт» чужой running;
- §63: отбор кандидатов пропускает неактивных, без гранта, `needs_reauth`
  и свежесинхронизированных; `sync_requested` делает должным немедленно и
  снимает паузу; порядок по due-time и лимит батча;
- §63/§64: backoff 2^n с капом 8×; `next_sync_at` = last_finished + backoff +
  персональный оффсет; оффсеты детерминированы и размазаны (40 аккаунтов
  ≠ один момент);
- §19: `SyncScheduler.scan_once` подаёт не больше свободных слотов,
  очередь дренируется без повторов, in-flight не пере-ставится;
  `sync_users` ограничен пулом и сохраняет порядок;
- воркер: `--once` — один ограниченный скан; без должных — чистый no-op.

Обновлены: `test_user_scoped_schema.py` (per-user sync-статус, санитизация,
счётчик падений, `reset_cache`), `test_user_isolation.py` (сид/проверки
`sync_status`, schema-guard — `sync_status` в множестве кэш-таблиц с
`user_id` в PK, а также что синк session-пользователя не трогает чужую
строку и не пишет ошибку при отсутствии гранта).

## 5. Проверки

- `pytest`: 93 passed (было 75).
- `ruff check` / `ruff format --check` (backend, tests, migrations): чисто.
- `pyright` (1.1.414, `pyrightconfig.json`): 0 errors.
- `alembic upgrade head --sql` на диалект postgresql: DDL `sync_status`
  компилируется; round-trip на чистой БД (`upgrade head` → `compare_metadata`)
  даёт пустой diff — миграция == метаданным. Против живого PostgreSQL, как и
  на этапе 3, не прогонялось — первая прод-проверка в этапе 10.
- `npm run lint` (eslint + tsc): чисто после перегенерации api-schema.
- Секретов в отслеживаемых исходниках нет; новых секретов не появилось.

## 6. Что осталось за пределами этапа 5

- **Этап 6 (API surface)**: `Teacher Mode and API Surface` — текущие
  учительские ручки уже user-scoped, но сверка списка §21+ будет там.
- **Этап 7 (фронтенд/конфиг)**: UI для sync-состояний (спиннер для queued/running
  через `syncing`, ретрай-подсказка на `error`, «войдите снова» на
  `needs_reauth`), рендер
  UTC-таймстемпов `last_sync` в локальной зоне, env-Host/CORS/trusted
  proxy, CSRF/security headers.
- **Этап 8 (desktop coexistence)**: смоук desktop-пути на собранном exe
  (desktop-цикл в этом этапе менялся только строкой состояния).
- **Этап 9 (rate limits/capacity)**: пересчёт `SYNC_MAX_WORKERS` ×
  `SYNC_MAX_CONCURRENT_USERS` против Google-квот и ёмкости БД.
- **Этап 10 (деплой)**: Docker/Compose с сервисом `worker`
  (`python sync_worker.py`), первая прогонка Alembic на живом PostgreSQL,
  много-пользовательский смоук.
- Не переносились старые значения `sync_state` (объяснено в ADR-0023):
  «last sync» на desktop пуст до ближайшего стартового синка.
