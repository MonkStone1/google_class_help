# Этап 4 — User Isolation: `get_current_user`, IDOR, user-scoped креденшелы и профиль

Реализация этапа 4 миграции на хостинг
(`docs/migration/User Isolation Part 1 num in query 4.md`, §12–§16;
`docs/migration/User Isolation Part 2 num in query 4.md`, §17, §67).
Опорные документы: аудит `HOSTING_MIGRATION_AUDIT.md`, результаты этапов 2
и 3 (`HOSTING_MIGRATION_STAGE2.md`, `HOSTING_MIGRATION_STAGE3.md`), решение
`docs/adr/adr-0022-user-isolation-get-current-user.md`.

Дата: 2026-09-20. Часть 1 (§12–§16) и часть 2 (§17, §67) реализованы.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §13 | Зависимость `get_current_user` в каждом data-эндпоинте | `ownership.get_current_user`: hosted → валидация cookie/сессии и загрузка `users`-record, desktop → синтетический локальный владелец. Выбор по `request.app.state.hosted` (не по процесс-флагу), чтобы desktop и hosted сосуществовали в одном процессе. Все ручки `api.py` принимают зависимость; id из запроса нигде не принимается |
| §13 | Не доверять `user_id` от фронтенда | сигнатуры ручек не содержат `user_id`; личность — только cookie сессии (hosted) или сам процесс (desktop) |
| §12 | Ревью каждого эндпоинта на IDOR | полный разбор ниже (§3); все чтения скоупятся `user_id`, непрямой доступ по угаданному Google-id → 404 |
| §12 | `DELETE /api/cache` стирает только кэш вызывающего | `clear_cache` зависит от текущего пользователя; `reset_cache(db, user_id)` (этап 3) вызывается с его id |
| §12 | `/api/status` не отдаёт чужое/глобальное состояние | hosted-ветка строит статус из session-пользователя (`users.display_name/email`), `last_sync` — из его `sync_state`; desktop-ветка по-прежнему читает loopback-аккаунт |
| §12 | `/api/sync` работает на данных вызывающего | `sync_now(user)` резолвит владельца и креденшелы из переданного пользователя; hosted-ручка передаёт session-пользователя |
| §14 | Разделение слоёв auth / Google-креденшелы / Classroom | `hosted_auth` — OAuth и сессии; новый `google_credentials` — токены и refresh; `classroom_api` — транспорт. Classroom-слой не решает, кто браузерный пользователь; токен из браузера нигде не принимается |
| §15 | User-scoped функции креденшелов | `google_credentials.get_google_credentials / save_google_credentials / refresh_google_credentials / delete_google_credentials`; две реализации за одним интерфейсом (hosted `oauth_tokens` / desktop `token.json`), выбор по `user.provider` |
| §15 | Refresh-лок per-user | `_refresh_lock_for(user_id)` (перенесён из `hosted_auth`); один пользователь не блокирует refresh другого, повторный refresh того же токена по-прежнему сериализуется (double-check под локом) |
| §16 | Никакого глобального `_login_state` для мультиюзера | hosted: per-attempt `oauth_login_states` + nonce-cookie (этап 2); в этом этапе hosted `/api/status` перестал читать desktop-глобал `_login_state`. Desktop-`_login_state` остаётся: desktop-сборка — один пользователь (зафиксировано в ADR-0022) |
| §16 | Пользователь не видит чужой OAuth URL/state/error | hosted auth-роуты только per-session; desktop-глобал недостижим в hosted-режиме (роутер hosted включается раньше) |
| §17 | Кэш профиля не глобальный, `user_id -> profile cache` | `api._profile_cache: dict[int, …]` — ключ по локальному `user_id`; hosted вообще не использует кэш, а читает строку `users` (профиль обновляется при входе, §7); desktop-владелец (пустая строка) ходит в userinfo один раз и кэшируется под своим id; сброс per-user |
| §67 | Очевидный путь владения в каждом ответе, без джойнов через пользователей | все ответы имеют один ownership-путь до `users.id` (зафиксировано в docstring `api.py`); у каждой таблицы кэша `user_id` в PK и во всех FK-цепочках; агрегатные джойны приравнивают `user_id` с обеих сторон; закреплено schema-guard и агрегатными тестами |

## 2. Файлы

Добавлено:

- `backend/google_credentials.py` — user-scoped слой Google-креденшелов
  (§14/§15): per-user refresh-локи, шифрование at-rest, две реализации за
  одним интерфейсом.
- `tests/test_user_isolation.py` — 28 тестов (§12–§17, §67).
- `docs/adr/adr-0022-user-isolation-get-current-user.md`.

Изменено:

- `backend/ownership.py` — `get_current_user` (§13); удалён устаревший шов
  `request_owner_id`.
- `backend/api.py` — все data-ручки зависят от текущего пользователя;
  `current_user_id` как тонкая производная; `/api/status` и `/api/sync`
  user-scoped; кэш профиля ключуется `user_id` (§17);
  `_build_auth_status(user)` объединён для обоих режимов; в docstring
  зафиксированы ownership-пути ответов (§67).
- `backend/hosted_auth.py` — токены/refresh вынесены в
  `google_credentials`; модуль владеет только OAuth-флоу и сессиями;
  `require_client_config` берётся из нового слоя.
- `backend/sync_service.py` — `sync_now(user)`; владелец и креденшелы из
  пользователя (`None` = локальный владелец desktop — фоновый цикл не
  изменился).
- `backend/auth.py`, `backend/main.py` — docstring/комментарии о границах
  этапа 4.
- `docs/adr/README.md` — зарегистрированы ADR-0021 (пропущен на этапе 3)
  и ADR-0022.
- `tests/test_api_auth.py`, `tests/test_hosted_auth.py` — под новые
  сигнатуры (`sync_now(user=...)`, `google_credentials.get_google_credentials`).

## 3. IDOR-ревью эндпоинтов (§12)

Все пути из списка §12; «скоуп» = используемая привязка к пользователю.

| Эндпоинт | Скоуп | Чужой id |
| --- | --- | --- |
| `GET /api/courses` | `Course.user_id == user.id` | строки другого пользователя не попадают |
| `GET /api/courses/{course_id}` | `db.get(Course, (user.id, course_id))` | 404 |
| `GET /api/courses/{id}/coursework` | `_get_course` + `CourseWork.user_id` | 404 |
| `GET /api/courses/{id}/students` | `_get_course` + teacher-gate + `CourseStudent.user_id` | 404 / 403 |
| `GET /api/courses/{id}/grades` | teacher-gate + `CourseWorkSubmission.user_id` | 404 / 403 |
| `GET /api/courses/{id}/coursework/{cw_id}` | PK `(user.id, cw_id)` + сверка `course_id` | 404 |
| `GET /api/courses/{id}/coursework/{cw_id}/submissions` | то же + `_submissions_for_work` по владельцу | 404 |
| `GET /api/courses/{id}/students/{sid}/grades` | `course_id`/`coursework_id` владельца; `student_id != "me"` требует роли TEACHER | 404 / 403 |
| `GET /api/assignments` (+`/upcoming`, `/overdue`) | `CourseWork.user_id` через `_load_assignments` | только свои задания |
| `GET /api/grades` | владелец + роль курса | только свои оценки |
| `GET /api/calendar` | `_load_assignments` по владельцу | только свои дедлайны |
| `GET /api/status` | сессия/локальный владелец + `sync_state(user_id)` | чужой профиль/статус недостижим |
| `POST /api/sync` | `sync_now(user)` — владелец и креденшелы вызывающего | чужой кэш не трогается |
| `DELETE /api/cache` | `reset_cache(db, user.id)` | удаляются только строки вызывающего |
| `GET/POST /api/auth/*` | hosted: per-session; desktop: один loopback-аккаунт | чужое состояние недостижимо (hosted-роутер перекрывает desktop) |

Непрямые пути: `Course`, `CourseWork`, `StudentSubmission`,
`CourseWorkSubmission`, `CourseStudent`, `CourseRole`, `SyncState` имеют
составные PK с `user_id` (этап 3); агрегатные джойны дополнительно
приравнивают `user_id` с обеих сторон (аудит §67). Угадывание Google-id
чужого coursework даёт 404, а не чужие данные (тест).

## 4. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| P3 | data-ручки читают все строки без фильтра | каждая ручка зависит от `get_current_user` и скоупится его id |
| P4 | `DELETE /api/cache` стирает весь кэш | только строки вызывающего (этап 3 + зависимость этапа 4) |
| P6 | `student_grades` проверял `student_id != "me"` только против роли | проверка идёт от аутентифицированного пользователя и его роли в курсе |
| P1/P2 | кэш профиля/статус без ключа пользователя | `_profile_cache` ключуется локальным `user_id` (§17); hosted-профиль/статус — из строки `users` сессии; пользователь B не может получить профиль A |
| A1/A5 | один `token.json`, креденшелы «текущего» пользователя | `google_credentials` + `oauth_tokens` в hosted; desktop-`token.json` только для локального владельца |
| A3 | `_refresh_lock` без ключа | per-user лок (`_refresh_lock_for`) |
| A2 | глобальный `_login_state` | hosted per-attempt state + nonce (этап 2); hosted-статус не читает desktop-глобал |
| A6 | после логина — один глобальный sync | `sync_now(user)`; per-user планировщик — этап 5 |

## 5. Тесты (75 всего, все зелёные)

Новые (`tests/test_user_isolation.py`):

- IDOR: чужой `course_id`/`coursework_id` (в т.ч. угаданный Google-id,
  отсутствующий у вызывающего) → 404; `/api/assignments`, `/api/grades`,
  `/api/courses` отдают только строки вызывающего; одинаковые Google-id у
  двух пользователей не смешиваются;
- `DELETE /api/cache` стирает только кэш вызывающего;
- `/api/sync` резолвит ровно одного пользователя — session-пользователя,
  и не трогает `sync_state` другого;
- §16: `/api/status` отдаёт имя/email/`last_sync` session-пользователя;
- §15: сохранение креденшелов per-user с шифрованием at-rest; удаление
  одного гранта не задевает другой; desktop-удаление разлинковывает
  `token.json`; provider-dispatch (local → desktop-бэкенд); per-user
  refresh-локи различны;
- §13: desktop-зависимость резолвит локального владельца; desktop data-ручка
  работает без сессии; 11 data-путей в hosted без сессии → 401;
- §17: кэш профиля keyed by user id (два пользователя — два независимых
  значения, повторный запрос не идёт в сеть, сброс одного не трогает
  другого); hosted-профиль берётся из строки `users` и глобальный кэш не
  заполняет;
- §67: schema-guard — у каждой из 7 таблиц кэша `user_id` в PK и все FK
  ведут только к ownership-колонкам (цепочка до `users.id`); агрегаты
  студента и матрица учителя при одинаковых Google-id двух пользователей
  не смешивают строки.

Обновлены: `test_api_auth.py` (`sync_now(user=...)`),
`test_hosted_auth.py` (`google_credentials.get_google_credentials`).

## 6. Проверки

- `pytest`: 75 passed (было 70 после части 1, 47 до этапа 4).
- `ruff check` / `ruff format --check` (backend, tests, migrations): чисто.
- `pyright` (1.1.414, `pyrightconfig.json`): 0 errors.
- Секреты в отслеживаемых исходниках не появлялись; новых секретов нет.

## 7. Что осталось за пределами этапа 4

- **Этап 5:** per-user синк/планировщик; сейчас `/api/sync` сериализован
  процесс-глобальным `_SYNC_LOCK`, а фоновая синхронизация в hosted
  отключена (локального владельца нет).
- **Этапы 7–10:** фронтенд (cookie/401), env-Host/CORS/trusted proxy,
  CSRF/security headers, Docker/Postgres-деплой, тесты мульти-пользователя
  на живом PostgreSQL.
- Остаётся необязательным из §66: переименование `DELETE /api/cache` в
  `DELETE /api/me/cache` (сейчас ручка уже user-scoped; переименование не
  входило в часть 1/2 и может быть сделано вместе с фронтендом на этапе 7).
