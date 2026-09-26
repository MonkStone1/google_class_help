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

- лимиты `web` 0.35 CPU / 256M, `worker` 0.45 / 384M, `postgres` 0.35 / 384M;
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
  run --rm --entrypoint python web /tools/loadtest_seed.py --users 20 --teachers 4
```

Скрипт создаёт пользователей, по сессии на каждого, курсы (один —
`ARCHIVED`, чтобы проверялся фильтр §61), coursework с разбросом сроков,
ростер и сдачи, а также строку `sync_status` в состоянии `ok`. Cookie
пишутся в `loadtest/session-cookies.txt`.

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
| RAM `web` ≤ 256M, `worker` ≤ 384M, `postgres` ≤ 384M | `watch-summary.json` |
| CPU не в насыщении | `watch-summary.json` + квота контейнера |
| соединения БД ≤ `DB_POOL_SIZE + DB_MAX_OVERFLOW` | `db-stats.csv` |
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
