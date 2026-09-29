# Нагрузочный прогон на локальном Docker-стенде (§88)

Как прогнать нагрузку на `compose.local.yml` и получить вердикт, который
можно вписать в чек-лист приёмки. Абсолютные цифры здесь **не** равны
продовым — об этом честно сказано в §7; локальный прогон отвечает на
другой вопрос: «не ломается ли сервис под нагрузкой и в каких пределах».

Инструменты (все — только стандартная библиотека Python, ничего нового в
образ не попадает, §73):

| Файл | Роль |
| --- | --- |
| `tools/load_test.py` | нагрузка: p50/p95/p99, статусы, RPS, open/closed loop |
| `tools/loadtest_seed.py` | синтетические пользователи, сессии и кэш |
| `tools/loadtest_watch.py` | CPU/RAM контейнеров + счётчики PostgreSQL в CSV |
| `tools/loadtest_report.py` | сводный вердикт PASS/FAIL по критериям §88 |
| `compose.loadtest.yml` | override с прод-профилем ресурсов (1 vCPU / 1 ГБ) |

Артефакты пишутся в `loadtest/`, который в `.gitignore`: там лежат cookie
сессий и дампы метрик.

---

## 1. Поднять стенд с прод-профилем

Зачем `compose.loadtest.yml`: локальная машина — 8 CPU / 32 ГБ, а прод — 1
vCPU / 1 ГБ (ADR-0028 §2.2). Без override контейнеры не ограничены, и
прогон измеряет девять свободных ядер вместо целевого сервера.

```powershell
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml config --quiet
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml build web
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml up -d postgres
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml run --rm --workdir /app web alembic -c /app/alembic.ini upgrade head
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml up -d web worker
```

Что задаёт override:

- лимиты `web` 0.55 CPU / 256M, `worker` 0.15 / 160M, `postgres` 0.30 / 288M
  (пересчитаны по замеру, ADR‑0028 §2.2.1);
- те же флаги PostgreSQL, что в `compose.yml` (`shared_buffers=128MB`,
  `work_mem=4MB`, `max_connections=30`, `effective_cache_size=512MB`);
- `GC_DASHBOARD_DB_POOL_SIZE=3`, `GC_DASHBOARD_DB_MAX_OVERFLOW=2`,
  `GC_DASHBOARD_SYNC_WORKERS=2`, `GC_DASHBOARD_SYNC_MAX_CONCURRENT_USERS=1`;
- **лимиты §39 и cooldown выключены** (`RATE_LIMIT_*=600`,
  `SYNC_MANUAL_COOLDOWN_SECONDS=0`): иначе S2–S4 упираются в 429 и
  измеряют лимитер, а не сервис. Проверка самих лимитов — отдельный прогон
  на **чистом** `compose.local.yml` (сценарий S6 ниже);
- сервис `loadgen` (профиль `loadtest`) — генератор нагрузки внутри
  docker-сети, ограничен 0.5 CPU, чтобы не отбирать ядра у `web`.

## 2. Наполнить кэш синтетическими пользователями

Все data-ручки закрыты сессионным гейтом (§50), поэтому нагрузка без
cookie измеряет только 401. Настоящий вход через Google для этого не нужен:
сессия — это случайный токен, в БД лежит только его SHA-256
(`models_auth.UserSession`), поэтому сессии можно выпустить локально.

```powershell
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml `
  run --rm --entrypoint python web /tools/loadtest_seed.py --users 20 --teachers 4 `
  --out /loadtest/session-cookies.txt
```

`--out /loadtest/...` обязателен: одноразовый контейнер работает с
`WORKDIR /app/backend`, поэтому путь без монтирования (`loadtest/...`)
остался бы внутри контейнера и пропал бы при выходе. `compose.loadtest.yml`
монтирует хостовый `loadtest/` как `/loadtest`, и `tools/load_test.py` затем
читает тот же файл с хоста.

Скрипт создаёт пользователей, по сессии на каждого, курсы (один —
`ARCHIVED`, чтобы проверялся фильтр §61), coursework с разбросом сроков,
ростер и сдачи, а также строку `sync_status` в состоянии `ok`. Cookie
пишутся в `loadtest/session-cookies.txt`.

Подключение к БД: скрипт читает `DATABASE_URL` из окружения и **снимает
суффикс драйвера** `+psycopg` перед передачей в psycopg — libpq такой
схемы не знает и иначе читает всю строку как conninfo
(`missing "=" after ...`). Как запасной путь принимаются libpq-переменные
`PGHOST`/`PGUSER`/`PGPASSWORD`/`PGDATABASE`.

Осознанные границы:

- `oauth_tokens` не создаются — фан-аут к Google у таких пользователей
  невозможен by construction, поэтому `google_requests`/`quota_errors`
  измеряются точечно на 1–2 настоящих аккаунтах (ADR-0027 §7);
- строки помечены `provider_subject LIKE 'loadtest-%'`; `--reset` удаляет
  только их, и без `--reset` скрипт откажется работать поверх существующих;
- обёмы: 20 пользователей × 4 активных курса × 20 работ = 1600 coursework.
  Больше — медленнее, а не «реалистичнее»: умножается на число запросов.


## 3. Запустить прогон

Два процесса: в одном окне — сэмплер ресурсов, в другом — нагрузка.

```powershell
# окно 1
python tools\loadtest_watch.py --duration 180 --out loadtest

# окно 2 — тот же запрос, который делает фронтенд при открытии дашборда
python tools\load_test.py --base-url http://127.0.0.1:8000 `
  --cookie-file loadtest\session-cookies.txt --per-path `
  --path /api/status --path /api/courses --path /api/assignments --path /api/grades `
  --requests 2000 --concurrency 4 --timeout 30 --warmup 100 `
  --json-out loadtest\run.json
```

Генератор внутри сети (не хостовый Python — так убирается шум проброса
портов Docker Desktop):

```powershell
docker compose --env-file .env.local -f compose.local.yml -f compose.loadtest.yml `
  --profile loadtest run --rm loadgen --cookie-file /data/session-cookies.txt --per-path --path /api/status
```

`load_test.py` шлёт `Sec-Fetch-Site: same-origin` и `Origin` на
unsafe-методах — иначе CSRF-проверка (§38) ответит 403 и прогон будет
измерять guard, а не эндпоинт.

Почему concurrency такой: `DB_POOL_SIZE + DB_MAX_OVERFLOW = 5` соединений,
и каждый sync-`def` эндпоинт FastAPI занимает поток anyio на время запроса
к БД. Пул — первое, что кончается, поэтому разумный старт — 4, а не 20;
рост конкуренции делают осознанно, чтобы увидеть границу.

Рядом с порогом 500 мс используйте `--repeat 3`: p95 — статистическая
величина, и её разброс между повторами на этом стенде — десятки
миллисекунд, то есть порог лежит прямо в шумовой полосе. Смотрите на
медиану и на разброс, а не на единственное число.

## 4. Вердикт

```powershell
python tools\loadtest_report.py --dir loadtest --load-json loadtest\run.json `
  --watch-json loadtest\watch-summary.json --collect-logs
```

Критерии и где они берутся:

| Критерий §88 | Источник |
| --- | --- |
| p95 ≤ 500 мс | `run.json` (`--max-p95-ms`) |
| 0 5xx, 0 transport errors | `run.json` |
| RAM `web` ≤ 256M, `worker` ≤ 160M, `postgres` ≤ 288M | `watch-summary.json` |
| CPU не в насыщении | `watch-summary.json` + квота контейнера |
| соединения БД ≤ пул × число процессов | `db-stats.csv` |
| очередь синка не растёт | `db-stats.csv` |
| нет `QueuePool`/OOM/трейсбеков, `quota_errors` не вырос | логи контейнеров |

Exit code: `0` — всё измеренное прошло, `1` — есть провал **или** критерий
не измерен. Неизмеренное намеренно не считается успехом: «мы не проверяли»
и «всё хорошо» не должны выглядеть одинаково в чек-листе.

## 5. Сценарии

| # | Сценарий | Пути |
| --- | --- | --- |
| S1 | public и статика | `/`, `/assets/index-*.js`, `/privacy/`, `/terms/`, `/api/health`, `/api/ready` |
| S2 | read-дашборд | `/api/auth/status`, `/api/status`, `/api/courses`, `/api/assignments` (ровно то, что шлёт `DataContext.loadData`) |
| S3 | тяжёлые агрегаты | `/api/grades`, `/api/calendar?from&to` |
| S4 | teacher-ручки | `/api/courses/{id}/students`, `/grades`, `/coursework`, `/submissions` |
| S5 | session gate | анонимный флуд на `/api/courses` → ожидается 401, не 500 |
| S6 | лимиты §39 | **на чистом** `compose.local.yml`: `GET /api/auth/login`, `POST /api/sync`, `DELETE /api/me/cache` |
| S7 | очередь синка | `POST /api/sync` от N пользователей; `sync_requested` растёт и возвращается к 0 |
| S8 | реальный фан-аут | один настоящий аккаунт: `google_requests` в логе воркера vs `capacity.REQUESTS_PER_TEACHER_SYNC = 40` |

Пример S6 (прод-лимиты, без override) — 70 запросов при лимите 60/мин:

```powershell
python tools\load_test.py --base-url http://127.0.0.1:8000 --method POST `
  --path /api/sync --cookie-file loadtest\session-cookies.txt `
  --requests 70 --concurrency 4 --expect-status 429 --json-out loadtest\run-s6.json
```

`--expect-status 429` меняет смысл вердикта: прогон проходит, только если
лимитер **сработал** и 5xx не было. Фактический прогон на стенде дал
61×200 + 9×429 с `Retry-After: 60` — лимит 60/мин отсёк ровно там, где
ожидалось.

## 6. Что делать по результатам

- **p95 вырос, соединения БД упёрлись в квоту** — сценарий pool-bound.
  Это ровно тот случай, для которого `DB_POOL_SIZE` и есть env-ручка;
  менять код не нужно (ADR-0028 §2.2).
- **CPU упирается в свою квоту (≥90 %)** — контейнер троттлился весь
  прогон. Абсолютные «проценты» тут бессмысленны: контейнер с
  `cpus: 0.35` не может показать больше ~35 %, поэтому отчёт считает
  насыщение относительно квоты.
- **`QueuePool` в логах** — соединения не возвращаются в пул. Пул
  расширить нельзя, это лечится в коде.
- **очередь синка растёт** — воркер не успевает; проверять §19/§63.

### 6.1 Найдено этим прогоном: deadlock при полном пуле (исправлено)

Первый же прогон на стенде с прод-профилем упал не по порогу, а насмерть:
при concurrency 6 процесс переставал отвечать **навсегда**, включая
`/api/health`, который БД не касается, и не восстанавливался без рестарта.

Как это выглядело:

```text
connections 5/5 заняты, все в состоянии idle in transaction
pg_stat_activity: wait_event_type = Client, wait_event = ClientRead
дамп потоков: все потоки anyio простаивают (queue.get),
              а поток event loop висит в QueuePool.get()
              → main.py require_session → hosted_auth.resolve_session_user
```

PostgreSQL при этом **не ждал ничего** (`ClientRead` = ждёт клиента), то
есть залипало приложение, а не база. Причина — блокирующий вызов БД прямо
в `async`-middleware: гейт сессии дёргал синхронный `resolve_session_user`
на event loop. Как только 5 соединений пула (прод-профиль 3+2) оказывались
заняты, цикл блокировался на `pool_timeout`, а cleanup зависимостей
(`get_db` → `finally: db.close()`) тоже выполняется на этом же цикле, поэтому
**ни одно соединение не возвращалось в пул** — кратковременная нехватка
превращалась в постоянную.

Исправление: гейт dispatch'ит lookup в worker-поток
(`await run_in_threadpool(...)`, `backend/main.py`). Регрессия закрыта
тестом `tests/test_stage8_coexistence.py::test_session_gate_dispatches_its_database_lookup_to_a_thread`.

Проверка на том же стенде с пулом 3+2:

| Прогон | До | После |
| --- | --- | --- |
| 120 запросов @ concurrency 8 | зависание, 0 ответов | **120/120 OK**, p95 341 мс |
| 240 запросов @ concurrency 16 | зависание | 240/240 OK, p95 891 мс, пул чистый |

После concurrency 16 латентность выше порога 500 мс — это честная
очередь на пул из 5 соединений, а не отказ: 0 ошибок, соединения вернулись
в `idle`, процесс продолжает отвечать. Если такая латентность неприемлема,
растёт `GC_DASHBOARD_DB_POOL_SIZE` (считая `max_connections=30` у БД) —
но это уже вертикальное масштабирование, а не баг.

### 6.2 Найдено этим прогоном: web не укладывается в отведённые 0.35 CPU

Прогон 2000 запросов @ concurrency 4 дал `p95 = 501.0 мс` (порог 500) и
`CPU saturation: web = 102% от своей квоты`. Первая мысль — «шум на
миллисекунде», но `--repeat 3` показал разброс p95 **494–507 мс**: порог
лежит ровно посреди шумовой полосы, так что единичный замер ничего не
разрешает. Разрешил A/B — смена квоты на живом контейнере, всё остальное
идентично (та же БД, тот же seed, те же 3 сессии, та же конкуренция):

| Рука | `cpus` у web | p50 | p95 (медиана) | разброс p95 | Пропускная |
| --- | --- | --- | --- | --- | --- |
| A — с квотой | 0.35 | 309 мс | 529 мс | 529–583 | 11.7 req/s · FAIL |
| B — без квоты | 8 | 117 мс | 229 мс | 222–251 | 30.0 req/s · PASS |

Разница **2.3–2.7×** при разбросе внутри руки ~10 % — эффект заведомо
не шум. Значит связывает **квота**, а не сам read-путь.

Сколько CPU на самом деле нужно (рука B, `docker stats` по CSV, 22 рабочих
сэмпла): **среднее 1.06 ядра, p50 1.13, p95 1.21, максимум 1.22** — то есть
весь рабочий период держится на ~1.1 ядра, а не всплескает. Отведённый
профиль — 0.35. **Разрыв трёхкратный.**

Что из этого следует, а что нет:

- Следует: профиль `compose.yml` / `compose.loadtest.yml` (ADR‑0028 §2.2)
  занижал CPU для web примерно втрое относительно измеренного read-нагрузки
  при 4 параллельных запросах. Квоты web+worker+postgres давали
  0.35+0.45+0.35 = 1.15 ядра, а с caddy и cloudflared — **1.35**, то есть
  **больше одного ядра**: все потребители заведомо не могли быть заняты
  одновременно. Профиль пересчитан (ADR‑0028 §2.2.1).
- Не следует: что VPS «не выдержит». Это ноутбук с Docker Desktop/WSL2;
  скорость ядра, накладные расходы и общая загрузка хоста другие. Прямой
  вывод про прод даёт только замер на VPS (чек-лист §8).

### 6.1 Третья рука: квота 0.55 (2026-09-26)

После пересчёта профиля тот же тест повторён на новой квоте
(4 пути, 1000 запросов × 3, concurrency 4, всё остальное идентично):

| Рука | `cpus` у web | p50 | p95 (медиана) | Пропускная | CPU web |
| --- | --- | --- | --- | --- | --- |
| A | 0.35 | 309 мс | 529 мс | 11.7 req/s | 100% квоты |
| B | **0.55** | 210 мс | **405 мс** | **16.4 req/s** | **103% квоты** |
| C | без квоты | 117 мс | 229 мс | 30.0 req/s | ~1.1 ядра |

Критерий §88 «p95 ≤ 500 мс» на руке B проходит, и это улучшение на 24% против
руки A. Но `loadtest_report.py` по-прежнему возвращает **FAIL по CPU
saturation**: web держится на 103% своей квоты весь прогон, postgres — на 90%
своей. То есть на одном ядре web всё ещё троттлится, и запаса по CPU нет.

Это главный аргумент за 2 vCPU: дело не в том, что 0.35 плох, а в том, что
одного ядра не хватает даже при правильно распределённых квотах.

Отдельно: `docker update --cpus 0` в этой версии Docker **не снимает квоту**
(возвращает успех, а `NanoCpus` остаётся прежним). Для A/B использовано
`--cpus 8`; всегда проверяйте `docker inspect --format
'{{.HostConfig.NanoCpus}}'`, иначе сравнение недостоверно.

## 7. Границы локального прогона

Честно, чтобы результат не выдавали за прод-измерение:

- Docker Desktop/WSL2 даёт цифры, отличные от VPS; здесь проверяется
  **корректность под нагрузкой** (нет 5xx, нет рестартов, нет утечек,
  лимиты работают), а не абсолютная ёмкость;
- Caddy и Cloudflare локально не подняты: статику отдаёт uvicorn, без gzip
  и без `request_body max_size 2MB` — измеряется web + PostgreSQL, не edge;
- сетевой задержки нет;
- один uvicorn-процесс (это совпадает с продом) и threadpool FastAPI для
  sync-`def` эндпоинтов;
- 1000 одновременных пользователей локально не воспроизвести: для этого
  есть сценарии 7–8 чек-листа и собственный замер на VPS.
