# Этап 3 — PostgreSQL, Alembic и user-scoped схема: результат

Реализация этапа 3 миграции на хостинг
(`docs/migration/PostgreSQL and Migrations num in query 3.md`, §10, §11,
§69, §71). Опорные документы: аудит `HOSTING_MIGRATION_AUDIT.md`,
результат этапа 2 `HOSTING_MIGRATION_STAGE2.md`, решение
`docs/adr/adr-0021-postgresql-alembic-user-scoped-schema.md`.

Дата: 2026-09-19.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §10 | PostgreSQL вместо SQLite как прод-стор | `database._build_engine()`: `DATABASE_URL` → PostgreSQL (psycopg 3, `pool_pre_ping`); hosted без URL — ошибка старта; SQLite остаётся только desktop-путь (ADR-0003) |
| §10 | User-scoped схема, корректная уникальность | Все 7 кэш-таблиц получили `user_id` (FK `users.id`, CASCADE) в PK; составные FK `(user_id, parent_id)`; индексы `(user_id, course_id)`; `uq_users_provider_subject` |
| §10 | «Не добавляй user_id вслепую» | Проанализированы PK и уникальности: Google id уникальны только в скоупе владельца; `CourseStudent.user_id` → `student_id` (M5); `sync_state` per-user (M4) |
| §11 | Alembic вместо `create_all` на проде | `alembic.ini`, `migrations/env.py` (URL из env, без URL отказ), ревизия `0001`; `init_db()`: SQLite → `create_all`, PostgreSQL → `alembic upgrade head` |
| §11 | Свежая установка поднимает полную схему | `0001` создаёт auth-таблицы этапа 2 + user-scoped кэш одной командой |
| §11 | Без «тихого» создания колонок | Автосоздание схемы вне Alembic для не-SQLite запрещено; контроль round-trip'ом (autogenerate после upgrade даёт пустой diff) |
| §69 | Совместимость типов/транзакций | Generic-типы SQLAlchemy (`JSON`, `Boolean`, `DateTime` naive-UTC); SQLite-прагмы только для SQLite-диалекта; `pool_pre_ping` против «server closed the connection»; апсёрты остаются ORM-уровнем (без raw `ON CONFLICT`) |
| §71 | Выделенная роль, least privilege | Инструкция и рекомендация двух ролей (owner для миграций + app DML) в `.env.example`; миграционные креденшелы — только у деплой-пайплайна |

## 2. Файлы

Добавлено:

- `backend/ownership.py` — шов владения кэшем: desktop → один синтетический
  локальный владелец; hosted → `request.state.user_id` от session-gate.
- `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`,
  `migrations/versions/0001_user_scoped_schema_with_auth_tables.py`.
- `tests/test_user_scoped_schema.py` — 11 тестов.
- `docs/adr/adr-0021-postgresql-alembic-user-scoped-schema.md`.

Изменено:

- `backend/models.py` — user-scoped схема кэша (все PK/FK), docstring.
- `backend/models_auth.py` — `uq_users_provider_subject`.
- `backend/database.py` — выбор движка, условные прагмы, Alembic в `init_db`.
- `backend/sync_store.py` — все операции с параметром `user_id` (запись,
  `get_submission`, purge, `reset_cache`, sync_state); `reset_cache` и purge
  скоупированы по владельцу (P4/Y3).
- `backend/sync_service.py` — владелец резолвится один раз на синк.
- `backend/api.py` — зависимость `_owner_id` (FastAPI `Depends`), все
  чтения/джойны скоупированы и приравнивают `user_id` по обе стороны (§67);
  `CourseStudent.user_id` → `student_id`.
- `backend/requirements.txt` — `psycopg[binary]>=3.2`, `alembic>=1.14`.
- `tests/conftest.py` — фикстура `owner_id`; сиды `test_student_grades.py` /
  `test_assignment_filters.py` обновлены под новые PK.

## 3. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| M1 | Нет `user_id` ни в одной кэш-таблице | `user_id` в PK всех 7 таблиц, FK на `users` с CASCADE |
| M2 | `Course.id` = Google id → PK-коллизия двух пользователей | PK `(user_id, id)`; два владельца держат одинаковый курс независимо (тест) |
| M3 | `StudentSubmission` PK без пользователя | PK `(user_id, course_id, coursework_id)` |
| M4 | Глобальный `sync_state` | `(user_id, key)`; статус синка per-user |
| M5 | `CourseStudent.user_id` — Google id студента, конфликт имён | Переименован в `student_id` |
| Y3 | purge «не вернулось — значит чужое» | `_purge_stale_courses(db, user_id, active_ids)` — скоупирован (тест) |
| P4/Y4 | `DELETE /api/cache` стирает всё | `reset_cache(db, user_id)` — только строки вызывающего (тест) |
| §67 | Джойны могли бы смешать строки разных пользователей | Все агрегатные джойны приравнивают `user_id` |

## 4. Тесты (47 всего, все зелёные)

Новые (`tests/test_user_scoped_schema.py`):

- одинаковый Google course id у двух пользователей — независимые строки (M2);
- `get_submission` / sync_state / purge / `reset_cache` уважают владельца;
- каскады: удаление пользователя уносит его кэш, удаление курса — его детей;
- локальный владелец создаётся ровно один раз;
- `DATABASE_URL` → PostgreSQL-диалект; hosted без URL → RuntimeError;
- end-to-end: две hosted-сессии видят только свой кэш
  (gate → `request.state.user_id` → `_owner_id` → скоупинг).

Обновлены сиды регрессионных тестов под составные PK.

## 5. Проверки

- `pytest`: 47 passed (было 36).
- `ruff check` / `ruff format --check`: чисто (backend, tests, migrations).
- `pyright`: 0 errors.
- `gitleaks` (проектный `.gitleaks.toml`): 0 находок.
- Alembic round-trip: `upgrade head` на чистой БД → autogenerate даёт
  пустую ревизию (миграция == метаданным); DDL всех таблиц компилируется
  под диалект `postgresql`. Против живого PostgreSQL миграция не
  прогонялась (сервера в среде разработки нет) — первая проверка на
  проде входит в этап 10 (деплой).

## 6. Что осталось за пределами этапа 3 (и почему)

- **Этап 4 (User Isolation):** `get_current_user` в сигнатурах ручек,
  IDOR-ревью каждого пути, рефакторинг `get_valid_credentials` →
  per-user (§15), login-state per-attempt (§16), per-user кэш профиля
  (§17). Сейчас скоупинг сделан швом `_owner_id` (session-gate уже
  кладёт id пользователя в `request.state`) — запросы скоупированы, но
  формализация зависимостей и аудит IDOR — этап 4.
- **Этап 5:** per-user синк/планировщик (сейчас `_do_sync` пишет кэш
  локального владельца; hosted синк отключён как и в этапе 2).
- **Этапы 7–10:** Docker/Compose с PostgreSQL, прод-деплой
  (`alembic upgrade head` в пайплайне), проверка миграции на живой БД.
- Миграция данных существующего desktop-SQLite в PostgreSQL не
  реализована (§11 допускает: только по явному требованию, отдельным
  скриптом).
