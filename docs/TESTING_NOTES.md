# Заметки по тестам и запуску проверок

Практические грабли, на которые уже наступали в этом репозитории. Читать
перед добавлением тестов и перед запуском `pytest`/линтеров.

Дата первого выпуска: 2026-09-21 (этап 6 миграции).

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
