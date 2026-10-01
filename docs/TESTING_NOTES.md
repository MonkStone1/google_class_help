# Заметки по тестам и запуску проверок

Практические грабли, на которые уже наступали в этом репозитории. Читать
перед добавлением тестов и перед запуском `pytest`/линтеров.

Дата первого выпуска: 2026-09-21 (этап 6 миграции).

**Последний полностью зелёный прогон: 2026-10-01** — `python -m pytest`
(432 passed), `cd frontend && npm run lint`, `npm run test` (25 файлов,
тестов), `npm run build`. `ruff check` и `pyright` — 0 ошибок.

---

## 8. Тикеты обратной связи (ADR-0035): новые файлы тестов

| Файл | Что проверяет |
| --- | --- |
| `tests/feedback_helpers.py` | общие хелперы (не тест): пользователи, сессии, `as_admin`, `SAFE_HEADERS` |
| `tests/test_feedback_tickets.py` | пользовательская поверхность: 401 анонимно, изоляция 404, неподделка личности, «ответ открывает решённый тикет», валидация, 429 |
| `tests/test_feedback_admin_auth.py` | админ-поверхность и разбор `ADMIN_EMAILS`: 403 всем, фильтры/поиск, два админа под разными именами, смена статуса, удаление |
| `tests/test_feedback_attachments.py` | вложения: снайфинг типа, active content, 413/422, обход каталога, авторизованная раздача, снятие файлов |

### Грабли, на которые уже наступали

- **`ADMIN_EMAILS` читается один раз при импорте `config`.** Тест, которому
  нужен администратор, патчит **уже разобранное множество**
  (`monkeypatch.setattr(config, "ADMIN_EMAILS", frozenset(...))`), а не
  окружение: `importlib.reload` работает, но оставляет модуль в изменённом
  состоянии для остальных тестов — обязательно делайте `monkeypatch.undo()`
  и повторный `reload`.
- **`request.form()` отдаёт `starlette.datastructures.UploadFile`, а не
  `fastapi.UploadFile`** (последний — подкласс). Проверка `isinstance` против
  fastapi-имени не сойдётся **никогда**, и загрузка молча пропадёт. Импортируйте
  `UploadFile` из `starlette.datastructures` в коде, работающем с формой.
- **`list[UploadFile]` инвариантен по элементу.** Если функция объявлена с
  `list[fastapi.UploadFile]`, а вызов передаёт `list[starlette.UploadFile]` —
  pyright ругается, и это не педантизм. Используйте `Sequence[UploadFile]`.
- **`pydantic.ValidationError` ловится отдельно от `ValueError`.** Enum-валидация
  (`FeedbackStatus("closed")`) бросает `ValueError`, а модель — `ValidationError`;
  `except Exception` здесь маскировал бы настоящие ошибки.
- **Модели в этом проекте без `relationship`.** `ticket.messages[0]` не
  существует — пишите `db.query(TicketMessage).filter_by(ticket_id=...)`.
- **Тест про 413 сравнивает содержимое каталога «до/после», а не «пусто».**
  `DATA_DIR` общий на всю сессию pytest, и каталог тикета `1` может содержать
  файлы, оставшиеся от другого теста.
- **Лимиты monkeypatch-ятся на модуле-потребителе**, а не на `config`:
  `feedback_service.FEEDBACK_TICKETS_PER_HOUR`, `feedback_attachments.
  FEEDBACK_MAX_ATTACHMENT_BYTES` — то, что endpoint реально читает.
  `ByteBudget` читает лимит в конструкторе специально ради этого.

### Форматирование

`ruff format` и `prettier --check` **не входят** в проверку §16, и репозиторий
до фидбека им не соответствовал (`backend/sync_store.py`,
`tests/test_sync_restart.py` и др. не отформатированы). Форматируйте только
**свои** новые файлы — иначе diff распухнет чужими правками.

---

## 9. Pylance в VS Code против `npx pyright` (не одно и то же)

`python -m pytest` и `npx pyright` могут быть зелёными, пока редактор
подсвечивает ошибки. Причины расхождения — не в коде:

| причина | где настраивается |
| --- | --- |
| **Интерпретатор.** Pylance берёт путь из строки состояния, а `venv`/`venvPath` из `pyrightconfig.json` — из CLI. Системный Python 3.13 на этой машине содержит `fastapi`, но **не** `sqlalchemy`/`alembic`: при его выборе «Import «sqlalchemy» could not be resolved» загораживается сразу в 32 файлах | `python.defaultInterpreterPath` в `.vscode/settings.json` |
| **Пути импорта.** Плоские импорты `from config import ...` (это же описано в `pytest.ini` → `pythonpath = backend` и в `ruff.toml` → `known-first-party`). Pylance читает **своё** `python.analysis.extraPaths`, а не поле `extraPaths` из pyright-конфига | `python.analysis.extraPaths` |
| **Набор файлов.** Pylance **игнорирует** `include` и анализирует всю рабочую область; CLI — только перечисленное. Поэтому `migrations` был добавлен в `include` | `include` в `pyrightconfig.json` |
| **Режим проверки.** Pylance не берёт режим из pyright-конфига. В `strict` дополнительно срабатывают `reportMissingParameterType` на `cls` в валидаторах Pydantic и `reportAny` на `**fields: Any` | `python.analysis.typeCheckingMode` |

Оба файла содержат комментарии и поясняют связь настроек; **менять их надо
вместе**. `npx pyright` — это проверка из консоли, а не из редактора:
он покажет 0 ошибок и не увидит проблемы Pylance, пока те не синхронизированы.

Что **не** является причиной: `reportMissingTypeStubs` (у fastapi, pydantic,
sqlalchemy, starlette и alembic есть `py.typed`), неиспользуемые импорты
(`ruff --select F401,F841` чисто) и `reportPrivateUsage` (мои файлы не
обращаются к `_приватным` именам чужих модулей).

### 9.1. «Ошибка на строке, которой нет» = устаревший буфер

Самый дорогой на диагностику случай. Pylance сообщил:

```
Line 123: Expected indented block
Line 175: "user" is not defined
Line 220: Type "TicketDetailOut" is not assignable to return type "list[UploadFile]"
Line 228: "(" was not closed
```

и отдельно по `schemas_feedback.py` — про строки **262** и **264**, тогда как
в файле **199 строк**.

Проверка за одну команду — ошибка в строке за пределами файла невозможна для
правильного содержимого:

```powershell
python -c "import ast,pathlib; ast.parse(pathlib.Path('backend/schemas_feedback.py').read_text(encoding='utf-8')); print('OK')"
(Get-Content backend\schemas_feedback.py | Measure-Object -Line).Lines
```

Если `ast.parse` проходит, а номер строки больше длины файла — Pylance
анализирует **не тот текст, что лежит на диске**. Причина: буфер во вкладке
открыт и не сохранён с момента, когда файлы правились снаружи (git, другой
инструмент, другой экземпляр редактора). Python и pytest читают диск и проходят,
Pylance — память редактора. Дальше ошибки идут каскадом: первая потеря
отступов («Expected indented block») ломает разбор, и последующие сообщения
про несуществующие переменные и типы бессмысленны — чинить их не нужно.

Лечение: `File: Revert File` (восстановит буфер из свежего диска), затем
`Python: Restart Language Server`, затем `Developer: Reload Window`. Правку
`.vscode/settings.json` Pylance подхватывает сам, перезагрузка нужна для
сброса состояния языкового сервера.

**Правило на будущее:** сначала сверяй номер строки с длиной файла и
`ast.parse`. Прежде чем «чинить» код по диагностике редактора, докажи, что
диагностика относится к текущему содержимому.

---

## 0. Нагрузочный прогон на локальном Docker-стенде

Полная процедура — `docs/LOAD_TEST_LOCAL.md`. Кратко, здесь только то, что
нужно знать перед любым другим тестом.

Инструменты нагрузки (только стандартная библиотека, ничего нового в образ
не попадает, §73):

| Файл | Роль |
| --- | --- |
| `tools/load_test.py` | нагрузка: p50/p95/p99, статусы, RPS, open/closed loop |
| `tools/loadtest_seed.py` | синтетические пользователи, сессии и кэш |
| `tools/loadtest_watch.py` | CPU/RAM контейнеров + счётчики PostgreSQL в CSV |
| `tools/loadtest_report.py` | сводный вердикт PASS/FAIL по критериям §88 |
| `compose.loadtest.yml` | override с прод-профилем ресурсов (1 vCPU / 1 ГБ) |

Артефакты (cookie сессий, CSV метрик) пишутся в `loadtest/`, который в
`.gitignore`.

```powershell
# стенд с прод-профилем (лимиты CPU/RAM как на VPS 1 vCPU / 1 ГБ)
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml build web
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml up -d postgres
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml run --rm --workdir /app web alembic -c /app/alembic.ini upgrade head
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml up -d web worker

# сессии: настоящий Google-логин не нужен, в БД лежит только SHA-256 токена.
# --out /loadtest/... обязателен: контейнер одноразовый, путь без монтирования
# пропал бы вместе с ним (compose.loadtest.yml монтирует ./loadtest → /loadtest).
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml run --rm --entrypoint python web /tools/loadtest_seed.py --users 20 --teachers 4 --out /loadtest/session-cookies.txt

# окно 1 — ресурсы, окно 2 — нагрузка
python tools\loadtest_watch.py --duration 180 --out loadtest
python tools\load_test.py --base-url http://127.0.0.1:8000 --cookie-file loadtest\session-cookies.txt --per-path --path /api/status --path /api/courses --requests 2000 --concurrency 4 --warmup 100 --json-out loadtest\run.json

# вердикт
python tools\loadtest_report.py --dir loadtest --collect-logs
```

Локальный прогон отвечает на вопрос «не ломается ли сервис под нагрузкой»,
а не «сколько пользователей выдержит прод»: Docker Desktop/WSL2, нет Caddy
и Cloudflare, нет сетевой задержки. Абсолютные цифры ёмкости — на VPS,
по чек-листу §8.

---

## 1. Запускать pytest через инструмент только с явным таймаутом

**Симптом:** `python -m pytest` уходит в бесконечность; весь ход агента/CI
зависает на несколько минут, потому что потока вывода нет и `tail` ждёт
завершения процесса.

**Почему:** в проекте нет `pytest-timeout` (проверено: `--timeout` не
распознаётся, `pytest.ini` его не подключает). Любой бесконечный цикл в
тесте или в моках, а также ожидание блокировки SQLite, не прерывается
самим pytest.

**Как запускать:**

- всегда передавай таймаут инструменту запуска (в pi/bash — параметр
  `timeout`, в секундах); без него не запускай прогон, который может
  зависнуть;
- сначала запускай один подозрительный тест/файл, а не весь `tests/`;
- для длинных прогонов фиксируй `pytest -x` (stop on first failure), чтобы
  не ждать оставшиеся тесты после первого сбоя.

## 2. Мок пагинации должен потреблять общую очередь страниц

**Симптом:** тест на пагинацию висит вечно, `nextPageToken` приходит снова
и снова.

**Причина:** мок-запрос копировал список страниц (`self._pages =
list(pages)`), поэтому каждый новый `list()` получал исходную очередь
заново — бесконечный цикл.

**Правило:** фейковый `execute()` обязан мутировать общий список страниц
(попу с фронта, без копии), чтобы следующий `list()` видел продолжение:

```python
class _FakeExecutable:
    def __init__(self, pages, calls):
        self._pages = pages      # ссылка, не list(pages)
        self._calls = calls

    def execute(self, num_retries=0):
        self._calls.append(num_retries)
        return self._pages.pop(0)
```

## 3. Фикстуры, чьи строки потом читает API, должны коммитить

**Симптом:** `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError)
database is locked` в тесте, который создаёт владельца/строку и сразу зовёт
эндпоинт.

**Причина:** фикстура делала только `flush()` (или ничего), её транзакция
оставалась открытой; API открывает отдельное SQLite-соединение и не может
ни прочитать, ни записать ту же таблицу.

**Правило:** если строка (в частности синтетический desktop-владелец из
`ownership.ensure_local_owner`) должна быть видна HTTP-запросу — делай
`db.commit()` до запроса. В `tests/conftest.py` фикстура `owner_id` это уже
делает; собственные seed-фикстуры тоже должны заканчиваться `commit()`.

## 4. Проверки этапа перед сдачей

Порядок, при котором не приходится перезапускать прогон:

1. `ruff check` и `ruff format --check` по `backend tests migrations`;
2. `python -m pytest tests/test_<новый>.py -q` с таймаутом на инструменте;
3. полный `python -m pytest -q` (тоже с таймаутом);
4. `pyright` (`pyrightconfig.json`);
5. для фронтенда — перегенерировать OpenAPI (`tools/dump_openapi.py` +
   `npm run gen:api:file`) и прогнать `npm run lint` — схема в
   `frontend/src/api-schema.d.ts` ломает `tsc` при расхождении.

## 5. Не держите блокирующий I/O на event loop

**Симптом:** под нагрузкой процесс перестаёт отвечать на всё, включая
эндпоинты, которые БД не трогают, и не восстанавливается без рестарта.

**Причина (найдена нагрузочным прогоном, §88):** `async`-middleware
вызывает синхронную функцию с запросом к БД. Event loop блокируется на всё
время запроса. Cleanup зависимостей FastAPI (`get_db` → `finally:
db.close()`) выполняется на том же цикле, поэтому при полном пуле
соединений **никто не возвращает соединение обратно** — кратковременная
нехватка превращается в вечную. Порог = `DB_POOL_SIZE + DB_MAX_OVERFLOW`
(прод: 3 + 2 = 5, ADR-0028 §2.2).

**Правило:** блокирующий вызов из `async`-контекста (собственный middleware
или endpoint) — только через `await run_in_threadpool(...)`, как это делает
`require_session` в `backend/main.py`. Синхронные `def`-эндпоинты FastAPI
выполняет в threadpool сам, там блокировки I/O допустимы.

**Как диагностировать зависший пул** (обе команды дешёвые, обе нужны):

```sql
select pid, state, wait_event_type, wait_event, xact_start, query
from pg_stat_activity where datname = current_database();
```

- `wait_event = ClientRead` при `idle in transaction` → PostgreSQL свободен,
  залипает приложение (как в этом случае);
- `wait_event_type = Lock` → реальная блокировка строк/таблиц в БД.

Плюс дамп всех потоков, если в образе/окружении доступен `faulthandler`:
`PYTHONFAULTHANDLER=1` в окружении процесса, затем `docker kill --signal=ABRT
<container>` — трейсбек всех потоков уходит в stderr контейнера и показывает,
где стоит event loop, а где простаивают worker-потоки.

## 6. `POSTGRES_PASSWORD` из env не меняет существующий volume

**Симптом:** `docker compose ... run --rm web alembic ...` падает с
`FATAL: password authentication failed for user "google_class_help_local"`,
хотя пароль в `.env.local` выглядит верным; `web` при этом уходит в
`Restarting`, `worker` не стартует.

**Причина:** `postgres:16-alpine` применяет `POSTGRES_PASSWORD` **только при
первой инициализации** каталога данных. Volume
`google-class-help-local_local_pgdata` уже был создан ранее (возможно, с
другим паролем), поэтому правка `.env.local` ни на что не влияет: Postgres
продолжает пускать по старому паролю. Локальный unix-сокет при этом
работает без пароля (trust), поэтому `docker exec ... psql` выглядит
рабочим и маскирует проблему.

**Как чинить, не теряя данные** (сокет доверяет, текущий пароль знать не
нужно):

```powershell
# 1. Собрать ALTER ROLE с паролем из .env.local, не печатая его:
$pw = (Get-Content .env.local | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' })`
        .Substring('POSTGRES_PASSWORD='.Length).Trim()
[IO.File]::WriteAllText("loadtest\fixpw.sql",
  "ALTER ROLE google_class_help_local WITH LOGIN PASSWORD '$($pw.Replace("'","''"))';`r`n")
# 2. Применить через локальный сокет (пароль не требуется):
$c = docker ps -q --filter 'name=google-class-help-local-postgres-1'
docker cp loadtest\fixpw.sql "${c}:/tmp/fixpw.sql" | Out-Null
docker exec $c psql -U google_class_help_local -d postgres -q -v ON_ERROR_STOP=1 -f /tmp/fixpw.sql
docker exec $c rm -f /tmp/fixpw.sql
```

Вариант «удалить volume» (`down -v`) уничтожает локальную БД вместе с
OAuth-токенами и кэшем — это не потеря конфигурации, а потеря данных,
поэтому применять только осознанно.

**Профилактика:** держите пароль URL-безопасным (буквы, цифры, `-`, `_`) —
тогда он одинаково переживает и `DATABASE_URL`, и `psql`; `.env.local.example`
это прямо требует. И помните: смена пароля в `.env.local` без `ALTER ROLE`
или `down -v` не делает ничего.

### 6.1 Почему пароль обязан быть URL-безопасным

**Симптом:** `alembic` падает не с «password authentication failed», а с
`ProgrammingError: invalid connection option "postgresql+psycopg://user:..."` —
то есть до сети дело не доходит, ломается **разбор DSN**.

**Причина:** пароль подставляется в `DATABASE_URL` без экранирования
(`compose.local.yml`: `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@...`).
Символы `=` и `&` имеют служебный смысл в URI (`=` начинает query-строку,
`&` разделяет параметры), поэтому пароль обрезается на первом же таком
символе, а остаток psycopg читает как неизвестные опции подключения.

**Правило:** `POSTGRES_PASSWORD` = только `[A-Za-z0-9_-]`. Длина — от
32 символов. Сгенерировать безопасно (не полагайтесь на
`[RandomNumberGenerator]::Fill` — в Windows PowerShell 5.1 этого статического
метода нет, и `New-Object byte[] N` даст нули, то есть пароль из одного
повторяющегося символа):

```powershell
$alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$bytes = New-Object byte[] 64
$rng.GetBytes($bytes)
$rng.Dispose()
$new = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
if ($new -notmatch '^[A-Za-z0-9_-]+$') { throw 'генерация дала не URL-безопасный пароль' }
```

После смены пароля в `.env.local` выполните §6 (ALTER ROLE) и
пересоздайте контейнеры: переменные окружения читаются при старте, поэтому
`docker compose ... up -d --force-recreate web worker` обязателен — иначе
контейнер продолжит работать со старым паролем и падать точно так же.

## 7. `dump_openapi.py` печатает минифицированный JSON

`tools/dump_openapi.py` делает `json.dump` без `indent`, а в репозитории
`frontend/openapi.json` хранится в формате prettier. Если просто
перенаправить вывод в файл, `git diff` покажет ~1400 строк «изменений»
форматирования вместо реальных правок схемы. После дампа прогоняй
prettier:

```bash
.venv/Scripts/python.exe tools/dump_openapi.py > frontend/openapi.json
cd frontend && npx prettier --write openapi.json && npm run gen:api:file
```
