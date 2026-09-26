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

# сессии: настоящий Google-логин не нужен, в БД лежит только SHA-256 токена
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml run --rm --entrypoint python web /tools/loadtest_seed.py --users 20 --teachers 4

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

## 5. `dump_openapi.py` печатает минифицированный JSON

`tools/dump_openapi.py` делает `json.dump` без `indent`, а в репозитории
`frontend/openapi.json` хранится в формате prettier. Если просто
перенаправить вывод в файл, `git diff` покажет ~1400 строк «изменений»
форматирования вместо реальных правок схемы. После дампа прогоняй
prettier:

```bash
.venv/Scripts/python.exe tools/dump_openapi.py > frontend/openapi.json
cd frontend && npx prettier --write openapi.json && npm run gen:api:file
```
