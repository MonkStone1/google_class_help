# ADR-0021: PostgreSQL, Alembic и user-scoped схема кэша

Дата: 2026-09-19
Статус: Accepted
Связанные: [ADR-0003](adr-0003-sqlite-cache-and-sync.md), [ADR-0017](adr-0017-teacher-mode.md), [ADR-0020](adr-0020-hosted-web-oauth-and-sessions.md)
Источник: `docs/migration/PostgreSQL and Migrations num in query 3.md` (§10, §11, §69, §71), аудит `docs/migration/audits/HOSTING_MIGRATION_AUDIT.md` (M1–M5, Y3, P4).

## Контекст

После этапа 2 (ADR-0020) появился локальный `users`/`sessions`/`oauth_tokens`,
но кэш Classroom (7 таблиц из ADR-0003) остался глобальным: первичные ключи —
голые Google id, значит два пользователя одного курса конфликтуют по PK и
делят одни строки (аудит M1–M4). Хостед-первичный стор — SQLite, схема
создаётся `create_all`, миграций нет. Этап 3 требует: PostgreSQL как
прод-база, Alembic как механизм миграций, user-scoped схема с корректной
уникальностью.

## Решение

### 1. Движок выбирается по конфигурации (§10, §69)

- `DATABASE_URL` из окружения → движок PostgreSQL (psycopg 3,
  `postgresql+psycopg://`, `pool_pre_ping=True`). URL — только env; в
  `alembic.ini` и в коде дефолтов нет.
- Хостед-режим (`GC_DASHBOARD_HOSTED=1`) без `DATABASE_URL` — ошибка
  старта (fail closed): SQLite не является хостед-первичной базой.
- Desktop-сборка продолжает работать на локальном SQLite-кэше
  (ADR-0003, coexistence — этап 8); SQLite-прагмы (WAL, busy_timeout,
  `foreign_keys=ON`) регистрируются только для SQLite-диалекта.
- Общие для обеих СУБД типы: `JSON`, `Boolean`, `DateTime` (naive UTC —
  соглашение бэкенда), generic-типы SQLAlchemy; PostgreSQL-нативные типы
  (JSONB и т. п.) не используются, т.к. конкретной выгоды нет, а
  совместимость с desktop-SQLite обязательна (§69: «Keep SQLAlchemy
  abstractions»).

### 2. Схема кэша становится user-scoped (§10)

Каждая кэш-таблица получила колонку `user_id` (FK `users.id`,
`ON DELETE CASCADE`) в составе первичного ключа; уникальность Google id —
только внутри одного пользователя:

```text
courses                  PK (user_id, id)                  # id = Google course id
coursework               PK (user_id, id)                  # id = Google coursework id
submissions              PK (user_id, course_id, coursework_id)
course_roles             PK (user_id, course_id)
course_students          PK (user_id, course_id, student_id)
coursework_submissions   PK (user_id, course_id, coursework_id, student_id)
sync_state               PK (user_id, key)                 # было глобальное last_sync (M4)
```

- Дочерние таблицы ссылаются на родителей составными FK
  `(user_id, parent_id) → parent(user_id, id)` с каскадом: удаление курса
  уносит ровно данные этого пользователя, удаление пользователя — весь его
  кэш (проверено тестами каскада).
- Внутренний суррогатный PK не введён: составные натуральные PK сохраняют
  апсёрт-паттерн синхронизации (ADR-0003) и минимально меняют код.
- `CourseStudent.user_id` (Google id зачисленного студента) переименован в
  `student_id`: колонка владельца называется `user_id` во всех таблицах,
  прежнее имя создавало коллизию смыслов (аудит M5).
- Добавлены `uq_users_provider_subject` (уникальность
  `(provider, provider_subject)` — бэкап апсёрта `_upsert_user`, §7) и
  составные индексы `(user_id, course_id)` для coursework/submissions.
- В `api.py` джойны агрегатов приравнивают `user_id` с обеих сторон
  (§67) — одинаковые Google id другого пользователя не могут утечь в
  чужой агрегат.

### 3. Alembic — единственный механизм схемы для PostgreSQL (§11)

- `alembic.ini` + `migrations/` (env.py берёт `DATABASE_URL` из окружения,
  без URL отказывается работать). Начальная ревизия `0001` создана
  autogenerate'ом и проверена round-trip'ом: `upgrade head` → повторный
  autogenerate даёт пустой diff, т.е. миграция == метаданным моделей.
- `database.init_db()`: SQLite → `create_all` (кэш расходный, ADR-0003);
  не-SQLite → `alembic upgrade head` (контролируемо, версионируемо,
  деструктивные изменения — отдельные ревизии на ревью).
- Автомиграция существующего локального SQLite не делается (§11: только по
  явному требованию); desktop-путь продолжит жить на `create_all`.

### 4. Шов владения кэшем (стадия-3 seams)

- `backend/ownership.py`: desktop-сборка владеет одним синтетическим
  локальным пользователем (`provider="local"`, `subject="desktop"`,
  создаётся один раз); hosted-запросы используют id сессии из
  `request.state.user_id`, который session-gate ставит до любой `/api`
  ручки. Хостед-контур синтетического «local»-пользователя никогда не
  создаёт (fail closed).
- Все операции `sync_store` (запись, purge, reset, sync_state) и все
  чтения `api.py` параметризованы `user_id`. `DELETE /api/cache` и
  mirror-purge стирают только строки вызывающего (P4/Y3).
- Граница с этапом 4: это не внедрение `get_current_user` в каждую ручку
  (§12–§13 — этап 4); это шов, который этап 4 заменит зависимостью, не
  меняя скоупинг запросов.

### 5. Роли PostgreSQL (§71)

Приложение использует выделенную роль (не суперпользователя); рекомендуемая
схема разделения (owner-роль для миграций + app-роль с DML) зафиксирована в
`.env.example`. Миграционные креденшелы не попадают в web-контейнер.

## Последствия

- Плюс: устранена коллизия PK между пользователями (M1–M4), появляется
  прод-база с версионированными миграциями, `reset_cache`/purge безопасны
  в мультиюзере уже сейчас.
- Плюс: desktop-путь не изменён (SQLite, create_all, ADR-0019); все 47
  тестов зелёные, включая изоляцию схемы и end-to-end hosted-изоляцию.
- Минус/долг: hosted-данные всё ещё не открываются наружу до этапа 4
  (ручки формально скоупированы швом `_owner_id`, но IDOR-ревью,
  `get_current_user` в сигнатурах и per-user креденшелы §15–§17 — этап 4);
  per-user sync — этап 5; миграция с существующих desktop-SQLite — только
  по явному требованию (§11).
- Начальная ревизия `0001` описывает ВСЮ схему сразу (auth-таблицы этапа 2
  + user-scoped кэш); свежая инсталляция PostgreSQL поднимается одной
  командой `alembic upgrade head`.
