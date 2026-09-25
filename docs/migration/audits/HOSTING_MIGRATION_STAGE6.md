# Этап 6 — Teacher Mode and API Surface: role gates, `/api/me`, identity и объём teacher-синка

Реализация этапа 6 миграции на хостинг
(`docs/migration/Teacher Mode and API Surface num in query 6.md`, §21–§25, §65).
Опорные документы: аудит `HOSTING_MIGRATION_AUDIT.md`, результаты этапов 2–5
(`HOSTING_MIGRATION_STAGE2.md`–`HOSTING_MIGRATION_STAGE5.md`), решение
`docs/adr/adr-0024-teacher-mode-api-surface.md`.

Дата: 2026-09-21. Все разделы промпта этапа 6 рассмотрены; §21/§22 закрыты
аудитом + точечными правками, §23–§25 и §65 реализованы.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §21 | Teacher-режим остаётся per-course и per-user | роль по-прежнему в `CourseRole(user_id, course_id)`; аккаунтного булева флага нет (ADR-0017/0024) |
| §21 | Teacher-only данные доступны только при «аутентифицирован + роль TEACHER» | явный `_require_teacher` на `.../students`, `.../grades`; `GET /api/courses/{id}` теперь отдаёт `students` только при роли TEACHER (раньше — безусловно); `.../submissions` ветвится по роли: учителю весь класс, студенту только своя строка |
| §21 | Read-only scopes сохранить, write/email не добавлять | набор из четырёх scope не тронут (`backend/auth.py`); pupil-email не запрашивается, письмо скрыто при отсутствии поля |
| §22 | Сохранить бизнес-смысл | закреплено тестами: missing ≠ 0, teacher-агрегаты ≠ личная сдача, архив скрыт, состояния явные, проценты согласованы (см. §3) |
| §23 | Привести `/api/...` к рабочему набору | добавлен `GET /api/me`; остальные маршруты §23 уже есть; дополнительные desktop-ручки сохранены, дубли не создавались |
| §23 | 401 без сессии / 403 без права / 404 вне скоупа | 401 — hosted-гейт и зависимость; 403 — `_require_teacher` и студент на чужого студента; 404 — чужой курс/coursework и студент не из ростера (вместо фабрикации пустой строки) |
| §24 | `/api/auth/status` описывает сессию текущего браузера, без OAuth-материала | `AuthStatus.user: UserOut`; hosted-статус отдаёт «свой» профиль, `auth_url=null`; токены/секреты/код не сериализуются (тест) |
| §25 | Web-логин ≠ desktop-логин | hosted: `GET /api/auth/login` → consent → `/api/auth/callback`; `POST /api/auth/login` → 405; loopback-URL остаётся только в desktop (ADR-0019) |
| §65 | User-level и глобальный лимиты, backoff, наблюдаемость, пагинация | per-user пул `SYNC_MAX_WORKERS` сохранён; добавлен процессный предел интерактивных синков (503 при исчерпании); backoff `num_retries` + расписание; `RequestStats` считает Google-запросы в лог; все list-методы идут по `nextPageToken` (тест) |

## 2. Файлы

Добавлено:

- `docs/adr/adr-0024-teacher-mode-api-surface.md` — решение этапа 6.
- `tests/test_teacher_mode.py` — 15 тестов (§21–§24).
- `tests/test_sync_volume.py` — 6 тестов (§65: лимит, счётчик, пагинация).
- `docs/TESTING_NOTES.md` — заметки по запуску pytest (таймаут, мок
  пагинации, коммит в фикстурах) — см. §7.

Изменено:

- `backend/schemas.py` — `UserOut`; `AuthStatus.user`.
- `backend/api.py` — `GET /api/me`, `_user_out`, `_build_auth_status`
  заполняет `user`; `course_detail` гейтит ростер ролью; `student_grades`
  404 для чужого студента; `run_sync` передаёт `interactive=True` и маппит
  `SERVER_BUSY` в 503; docstring про §21–§24.
- `backend/hosted_auth.py` — `hosted_status` отдаёт вложенный `user`.
- `backend/classroom_api.py` — `RequestStats` + единая точка
  `_execute()` (backoff + счётчик) для всех запросов.
- `backend/sync_service.py` — `SERVER_BUSY`, процессный предел
  интерактивных синков, `sync_now(..., interactive=...)`,
  `_thread_local_client(..., stats)`, лог `google_requests`/длительности.
- `backend/sync.py` — фасад экспортирует `SERVER_BUSY`.
- `backend/config.py` — `SYNC_MAX_CONCURRENT_USERS` переиспользован как
  общий предел (комментарий); новых переменных окружения нет.
- `tests/conftest.py` — фикстура `owner_id` коммитит владельца (иначе
  SQLite «database is locked» при чтении из API).
- `tests/test_api_auth.py` — моки `sync_now` принимают новый kwarg.
- `frontend/openapi.json`, `frontend/src/api-schema.d.ts` — перегенерированы
  (`tools/dump_openapi.py` + `npm run gen:api:file`); `tsc`/eslint проходят.
- `.env.example` — комментарий, что `SYNC_MAX_CONCURRENT_USERS` ограничивает
  и ручной `POST /api/sync`.
- `docs/adr/README.md` — зарегистрирован ADR-0024.

## 3. Аудит §21/§22 (что проверено и что поправлено)

**§21 — teacher-режим.** Роль per-course (ADR-0017), кэш и креденшелы
user-scoped (ADR-0021/0022), teacher-эндпоинты уже зависят от
`get_current_user`. Найденные слабые места и правки:

| Место | Было | Стало |
| --- | --- | --- |
| `GET /api/courses/{id}` | `students` отдавался безусловно; остаточный ростер прошлого «учительского» периода мог вытечь студенту того же аккаунта | `students` только при `role == TEACHER` |
| `GET /api/courses/{id}/students/{sid}/grades` | учитель на неизвестного студента получал 200 с выдуманной строкой | 404, если студент не из ростера |
| `.../students`, `.../grades` | уже `_require_teacher` | без изменений |
| `.../coursework/{cw}` и `.../submissions` | роль не проверялась явно, но данные ветвились по роли | оставлено: обе роли, но чужие данные недостижимы (проверено тестами на двух пользователей в `test_user_isolation`) |
| SCOPES | четыре read-only | без изменений, write/email-scope не добавлялись |

**§22 — семантика.** Проверено по коду и закреплено тестами: `grade_percent`
возвращает `None` без оценки; `derive_submission_status` различает
`not_submitted/turned_in/returned/graded`; teacher-агрегаты отдельны от
личных полей; `course_state == "ARCHIVED"` фильтруется в `_get_course`,
`_load_assignments`, `_course_stats_sql`; клиентские календарь/поиск/фильтры
(ADR-0009/0012/0013) не переносились на сервер. Один и тот же балл даёт
одинаковый процент в матрице, coursework и карточке студента (тест).

## 4. §65 — объём teacher-API

- **Per-user**: один общий пул `SYNC_MAX_WORKERS` на весь sync (ADR-0014);
  teacher-этапы (`courseWork.list` всех состояний, `students.list`,
  `studentSubmissions.list` c `courseWorkId="-"`) идут через него.
- **Global**: планировщик подаёт не больше `SYNC_MAX_CONCURRENT_USERS`
  пользователей (ADR-0023); ручной `POST /api/sync` теперь тоже берёт
  процессный слот и при исчерпании отвечает 503 (`SERVER_BUSY`), а не
  открывает новый пул. Плановые синки под счётчик не попадают — их
  ограничивает пул планировщика; смешение дало бы ложные «failed» в
  `sync_status`.
- **Backoff**: `num_retries` (googleapiclient) на каждый запрос +
  экспоненциальный backoff расписания по `consecutive_failures` (ADR-0023).
- **Observability**: `RequestStats` — один счётчик на sync, общий для
  потоковых клиентов; в лог успеха/падения пишется `google_requests` и
  длительность. В БД/API счётчик не выносится (операционная метрика).
- **Pagination**: все list-методы идут по `nextPageToken` до конца;
  проверено на фейковом discovery-сервисе (2 страницы → 2 запроса).

## 5. Тесты (115 всего, все зелёные; было 93)

Новые (`tests/test_teacher_mode.py`, 15):

- §21: `.../students` и `.../grades` → 403 для студенческого курса;
  карточка курса скрывает/показывает ростер по роли;
- §22: ungraded `TURNED_IN` → `points/percent = None`, `status = turned_in`,
  вклад в средний 0; teacher-агрегаты не попадают в личные поля и в
  `/assignments`/`/grades`; одинаковый процент во всех представлениях;
  архивный курс отсутствует в `/courses`, даёт 404 на карточку и coursework;
- §23: неизвестный студент у учителя → 404; студент на чужого → 403;
  `/api/me` в hosted без сессии → 401;
- §24: desktop `/api/me` = локальный владелец; `auth/status` несёт вложенный
  `user`, совпадающий с плоскими полями, и никакого OAuth-материала;
  hosted `/api/me`/статус описывают session-пользователя; два браузера не
  путают имена; hosted-запрос не создаёт desktop-владельца.

Новые (`tests/test_sync_volume.py`, 6):

- §65: при исчерпании глобального слота `POST /api/sync` → 503; `sync_now`
  без слота → `SERVER_BUSY`; плановый (`interactive=False`) синк не
  упирается в интерактивный предел;
- §65: пагинация `courses.list` и teacher-sweep `studentSubmissions`
  (`courseWorkId="-"`) идёт по токену; каждый запрос посчитан; `RequestStats`
  потокобезопасен (8 потоков × 100).

Обновлены:

- `tests/conftest.py` — `owner_id` коммитит владельца;
- `tests/test_api_auth.py` — моки `sync_now` принимают `**kwargs`.

## 6. Проверки

- `pytest`: 115 passed (было 93).
- `ruff check` / `ruff format --check` (backend, tests, migrations): чисто.
- `pyright` (1.1.414, `pyrightconfig.json`): 0 errors.
- `npm run lint` (eslint + tsc): чисто после перегенерации api-schema.
- Секретов в отслеживаемых исходниках нет; новых секретов нет.

## 7. Заметки по процессу проверок (записано, чтобы не повторять)

Вынесено в `docs/TESTING_NOTES.md`; главное:

1. **pytest запускать только с явным таймаутом инструмента.** В проекте нет
   `pytest-timeout`; бесконечный цикл в тесте/моке вешает весь прогон
   (на этапе 6 так «зависли» на ~6 минут без вывода). Сначала одиночный
   файл, потом весь `tests/`, и всегда с таймаутом.
2. **Мок пагинации должен потреблять общую очередь страниц.** Копия списка
   (`self._pages = list(pages)`) заставляла `nextPageToken` приходить снова —
   бесконечный цикл; фейковый `execute()` обязан мутировать общий список.
3. **Фикстуры, чьи строки читает API, должны коммитить.** Незакоммиченная
   транзакция в `db`-сессии даёт `sqlite3.OperationalError: database is
   locked` на запросе из другого соединения; `owner_id` теперь коммитит.

## 8. Что осталось за пределами этапа 6

- **Этап 7 (фронтенд/конфиг):** переключить UI на `AuthStatus.user`/
  `GET /api/me`, cookie-сессия и обработка 401/403/503, спиннер на
  `sync_status`, рендер UTC `last_sync` в локальной зоне, env-Host/CORS,
  CSRF/security headers, удаление плоских `user_name`/`user_email`.
- **Этап 8 (desktop coexistence):** смоук desktop-пути на собранном exe
  (менялись только внутренние проверки, desktop API не тронут).
- **Этап 9 (rate limits/capacity):** по `google_requests` из логов
  пересчитать `SYNC_MAX_WORKERS × SYNC_MAX_CONCURRENT_USERS` против квот;
  при необходимости — межпроцессный предел и персистенция метрик.
- **Этап 10 (деплой):** много-пользовательский смоук teacher-сценария на
  живом PostgreSQL (teacher + student у одного аккаунта, архив, чужие id).
