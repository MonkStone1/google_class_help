# ADR-0022: User isolation — get_current_user и user-scoped Google-креденшелы

Дата: 2026-09-20
Статус: Accepted
Связанные: [ADR-0003](adr-0003-sqlite-cache-and-sync.md), [ADR-0017](adr-0017-teacher-mode.md), [ADR-0019](adr-0019-oauth-flow-owned-by-app.md), [ADR-0020](adr-0020-hosted-web-oauth-and-sessions.md), [ADR-0021](adr-0021-postgresql-alembic-user-scoped-schema.md)
Источник: `docs/migration/User Isolation Part 1 num in query 4.md` (§12–§16) и `docs/migration/User Isolation Part 2 num in query 4.md` (§17, §67), аудит `docs/migration/audits/HOSTING_MIGRATION_AUDIT.md` (P3, P4, P6, A1–A3, A5, C1, M1–M5).

## Контекст

Этап 3 сделал схему кэша user-scoped (PK с `user_id`), но доступ к ней
шёл через шов `ownership.request_owner_id`: в hosted-режиме он брал
`request.state.user_id`, который выставлял session-gate-middleware. Это
работало, однако:

- ручки не зависели от пользователя явно — доверяли состоянию, которое
  выставил middleware раньше в цепочке (`_owner_id` без валидации);
- креденшелы Google в hosted-режиме уже были per-user (`oauth_tokens`,
  `get_valid_credentials_for` в `hosted_auth.py`), но жили в модуле,
  который одновременно владеет OAuth-флоу, сессиями и токенами — слои
  (§14) были смешаны;
- `/api/status` и `/api/sync` в hosted-режиме всё ещё обращались к
  desktop-глобалам (`auth.login_status()`, `auth.get_valid_credentials()`,
  `sync_now()` без пользователя): первый показывал чужое/глобальное
  состояние логина, второй мог синхронизировать локального владельца
  вместо вызывающего.

Промпт этапа 4 (§12–§16) требует: явную зависимость `get_current_user`,
закрытие IDOR на каждом пути, разделение слоёв «аутентификация →
Google-креденшелы → Classroom», user-scoped функции креденшелов и
отсутствие глобального состояния логина в мультиюзере.

## Решение

### 1. Одна зависимость текущего пользователя (§13)

`ownership.get_current_user(request, db) -> User` — FastAPI-зависимость,
которую принимает каждый data-эндпоинт. Она выбирает бэкенд по экземпляру
приложения (`request.app.state.hosted`, а не по процесс-флагу — так тесты
держат desktop и hosted приложения рядом):

- hosted → `hosted_auth.get_current_user`: cookie читается, сессия
  валидируется (`sessions`: отсутствует/истекла/отозвана → 401),
  активный `users`-record загружается;
- desktop → синтетический локальный владелец (loopback OAuth не знает
  сессий, процесс — один пользователь, ADR-0019).

Ручки никогда не принимают `user_id` из запроса. Эндпоинтам, которым
нужен только id владельца кэша, отдаётся тонкая производная
`api.current_user_id` (тот же `get_current_user` внутри); `/api/status` и
`/api/sync` берут сам объект пользователя. Session-gate-middleware
остаётся (ADR-0020) как самая внешняя проверка, но авторитетной является
зависимость в ручке.

### 2. Отдельный слой Google-креденшелов (§14, §15)

Новый модуль `google_credentials.py` — единственный способ получить
креденшелы. Интерфейс §15:

```python
get_google_credentials(db, user)      # валидные Credentials | None
save_google_credentials(db, user_id, creds)
refresh_google_credentials(db, user)  # принудительный refresh
delete_google_credentials(db, user_id)
```

Внутри — две реализации за одним интерфейсом, выбор по `user.provider`:

- `google` (hosted): строка `oauth_tokens(user_id)`, шифрование at-rest
  (ADR-0020), refresh под **per-user** локом; `auth.refresh_credentials`
  переиспользуется как транспорт;
- `local` (desktop): единственный `token.json` процесса (ADR-0019) —
  у desktop ровно один пользователь, поэтому его единичный лок и есть
  user-aware.

`hosted_auth.py` больше не владеет токенами: он берёт `require_client_config`
и `save_google_credentials` из нового модуля. OAuth-флоу и сессии остаются
в нём. `classroom_api.py` не решает, кто браузерный пользователь, и не
принимает токен от фронтенда (§14) — это было верно и раньше, теперь
подтверждено структурой модулей.

### 3. Синхронизация по пользователю (§12)

`sync_service.sync_now(user=None)`: владелец кэша и креденшелы резолвятся
из переданного пользователя (`None` = локальный владелец desktop, поэтому
фоновый цикл desktop не меняется). `/api/sync` передаёт session-пользователя.
Мьютекс синка пока процесс-глобальный (один синк за раз на процесс) —
ограничение зафиксировано здесь и снимается per-user-планировщиком на
этапе 5.

### 4. Состояние логина (§16)

- Hosted: попытки логина корректно привязаны к браузеру через
  `oauth_login_states` + nonce-cookie (реализовано на этапе 2); в этом
  этапе `/api/status` в hosted-режиме перестал читать desktop-глобал
  `_login_state` и строит статус из session-пользователя.
- Desktop: `_login_state` и `_refresh_lock` в `auth.py` остаются
  глобальными — это безопасно, потому что desktop-сборка обслуживает
  ровно одного пользователя; hosted их не читает.

### 5. IDOR-ревью (§12)

Все перечисленные в §12 пути скоупятся `user_id` (составные PK и
`filter(... user_id == ...)`), включая джойны, которые приравнивают
`user_id` с обеих сторон (§67, этап 3). Непрямой доступ по угаданному
Google-id невозможен: PK `CourseWork`/`Course`/`Submission` включают
владельца, а `_get_course`/`_assignment_by_id` возвращают 404 для чужого
id. Право студента видеть только свои оценки проверяется против
`get_current_user` (роль курса), а не против строки-сентинела.

### 6. Профиль пользователя — user-scoped кэш (§17)

Кэш профиля перестал быть одним глобальным значением:

```python
_profile_cache: dict[int, tuple[float, str | None, str | None]]
```

Ключ — локальный `user_id`. Профиль резолвится так:

1. если в строке `users` уже есть `display_name`/`email` (hosted: они
   обновляются из Google при каждом входе, §7) — возвращается значение
   строки, кэш не задействован и сети нет;
2. иначе (desktop-владелец: его строка пуста) — один запрос userinfo и
   запись в кэш под `user.id` на 5 минут.

Сброс (`_reset_profile_cache`) тоже per-user: logout удаляет только запись
вызывающего. Пользователь B не может получить имя/email пользователя A —
ни из кэша, ни из строки другого пользователя: и чтение, и запись идут по
`user_id`, а сама зависимость уже гарантирует нужного пользователя (§13).

`_build_auth_status(user)` объединён для обоих режимов: hosted — статус из
строки сессии, desktop — loopback-состояние плюс per-user кэш профиля.

### 7. Ownership путей в ответах (§67)

У каждого ответа с данными пользователя один явный путь владения до
`users.id` (зафиксировано в docstring `api.py`):

```text
CourseOut / CourseDetailOut         → Course.user_id
AssignmentOut / AssignmentDetailOut → CourseWork.user_id → Course.user_id
StudentGradesOut                    → CourseWork/Course.user_id
                                      + StudentSubmission.user_id
TeacherGradesOut                    → CourseStudent / CourseWorkSubmission
                                      → Course.user_id
SubmissionOut                       → CourseWorkSubmission.user_id (teacher)
                                      или StudentSubmission.user_id (student)
SyncStatus / AuthStatus             → аутентифицированный пользователь
```

Путь структурный, а не только соглашение: у каждой таблицы кэша `user_id`
входит в PK и во все FK-цепочки (models.py, §10), поэтому строки без
владельца не существует, а совпадающий Google-id уникален лишь в скоупе
одного пользователя. Агрегатные джойны приравнивают `user_id` с обеих
сторон. Оба инварианта закреплены тестами (`tests/test_user_isolation.py`:
schema-guard по всем таблицам и проверки агрегатов/матрицы при одинаковых
Google-id у двух пользователей).

## Последствия

- Плюс: явная, тестируемая граница изоляции; каждая ручка отвечает 404/403
  на чужие id; креденшелы и refresh-локи строго per-user; hosted-статус
  не смешивается с desktop-состоянием.
- Плюс: слои разделены — OAuth/сессии (`hosted_auth`), креденшелы
  (`google_credentials`), транспорт (`classroom_api`), владение кэшем
  (`ownership`).
- Плюс: профиль нигде не хранится глобально (§17), а путь владения
  каждого ответа зафиксирован и защищён schema-guard тестом (§67).
- Минус: в hosted-запросе сессия резолвится дважды (gate + зависимость) —
  два индексных SELECT; принято сознательно ради defense-in-depth.
- Ограничение: `/api/sync` сериализует синки всех пользователей
  процесс-глобальным мьютексом до этапа 5.
- Desktop-поведение не изменилось: локальный владелец, `token.json`,
  gate по Host/Origin, фоновый синк.
