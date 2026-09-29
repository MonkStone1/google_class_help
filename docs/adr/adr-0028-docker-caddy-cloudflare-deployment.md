# ADR-0028 — Docker/Compose/Caddy + Cloudflare Tunnel деплой и queued-синк

Статус: Accepted. Дата: 2026-09-24. Этап 10 миграции на хостинг
(`docs/migration/Testing and Deployment Part 1–4 num in query 10.md`,
§52–§88) плюс `docs/prompt/GoogleClassHelp_DDoS_Security_Code_Changes.md`
как дополнение по защите от абьюза.

## 1. Контекст

Этапы 1–9 сделали модель приложения мульти-пользовательской: web OAuth и
сессии (ADR-0020), PostgreSQL + user-scoped схема (ADR-0021), user isolation
(ADR-0022), per-user синк (ADR-0023), teacher-гейты (ADR-0024), production
frontend/edge (ADR-0025), разделение desktop/hosted (ADR-0026), лимиты и
capacity (ADR-0027). Оставалось собрать это в развёртывание: контейнеры,
обратный прокси, БД, бэкапы, readiness и финальная приёмка.

Целевой хост — **один VPS 1 vCPU / 1 GB**, домен `monkstonecor.pp.ua`,
внешняя защита — **Cloudflare Free + Tunnel** (origin без входящих портов).
DDoS-док предлагал 2 vCPU / 2 GB; владелец выбрал 1/1, поэтому лимиты
пересчитаны вниз, а не вверх.

## 2. Решения

### 2.1 Контейнеры (§54–§56, DDoS §4)

Пять сервисов на приватной docker-сети, наружу — ничего:

```text
Internet → Cloudflare (TLS, DDoS) → Tunnel → cloudflared
                                                 ↓
                                            caddy:80
                                                 ↓
                                            web:8000 → postgres:5432
                                            worker   → postgres:5432
```

- `web` — `uvicorn main:app` из образа `google-class-help:local`;
- `worker` — тот же образ, `python sync_worker.py` (ADR-0023, Option A);
- `postgres:16-alpine` — только `expose: 5432`, volume `pgdata`, tuning под
  1 GB (`shared_buffers=128MB`, `work_mem=4MB`, `max_connections=30`);
- `caddy:2-alpine` — только `expose: 80`, конфиг `Caddyfile` (read-only);
- `cloudflared` — outbound-tunnel, `CLOUDFLARE_TUNNEL_TOKEN` из `.env`.

Dockerfile — двухстадийный: Node собирает `frontend/dist`, Python 3.12-slim
ставит только `backend/requirements-prod.txt` (пины §73) и запускается под
non-root `app` (§22). `--proxy-headers` у uvicorn СОЗНАТЕЛЬНО выключен:
доверие к `X-Forwarded-*` решает `backend/proxy.py` по
`GC_DASHBOARD_TRUSTED_PROXIES` (§29), иначе uvicorn переписал бы
`request.client` до проверки.

### 2.2 Ресурсный профиль 1 vCPU / 1 GB (§40/§88)

| Параметр | Значение | Почему |
| --- | --- | --- |
| `SYNC_MAX_WORKERS` | 2 | один синк держит сеть+парсинг+запись; 8 потоков уронили бы web |
| `SYNC_MAX_CONCURRENT_USERS` | 1 | бюджет 2×1 = 2 потока на весь бокс |
| `SYNC_INTERVAL_MINUTES` | 30 | ~200 req/min на 1000 юзеров вместо ~600 при 10 мин |
| `SYNC_STARTUP_STAGGER_SECONDS` | 600 | анти-стартовый шторм после деплоя (§64) |
| DB pool | 3 + 2 overflow | синк не держит коннект через Google-фетч (§45) |
| compose limits | web 0.55cpu/256M, worker 0.15cpu/160M, postgres 0.30cpu/288M, caddy 0.1/48M, cloudflared 0.1/32M | пересчитано по замеру, см. §2.2.1 |

`capacity.py` остаётся источником арифметики; прод-значения задаются в
`.env`, код-дефолты не менялись. Сигнал к апгрейду до 2/2 — глубина очереди,
`duration` синка, 5xx по метрикам (§25 DDoS-дока, ADR-0027 §7).

#### 2.2.1 Пересчёт лимитов по результатам замера (2026-09-26)

Изначальный профиль (`web .35, worker .45, postgres .35`) был подобран на глаз и
оказался неверным по двум независимым причинам.

**1. Квота web была втрое ниже измеренной потребности.** Локальный стенд
(ADR‑0028 §2.2, `compose.loadtest.yml`) при 4 параллельных запросах к
`/api/status`, `/api/courses`, `/api/assignments`, `/api/grades` устойчиво
держал ~1.1 ядра. A/B-прогон одного и того же теста:

| Прогон | квота web | p95 | пропускная | CPU web |
| --- | --- | --- | --- | --- |
| A | 0.35 | 529 мс | 11.7 req/s | 100% квоты (троттлинг) |
| B (новый) | 0.55 | **405 мс** | **16.4 req/s** | **103% квоты** |
| C (референс) | без квоты | 229 мс | 30.0 req/s | ~1.1 ядра |

**2. Сумма квот превышала одно ядро** (0.35+0.45+0.35+0.1+0.1 = 1.35), то есть
три потребителя заведомо не могли работать одновременно. Новый профиль — 1.20
(cpu) и **784M RAM** из 1024M; ~240M остаётся ОС, Docker и page cache. Сумма
1.20 > 1.0 здесь допустима осознанно: caddy и cloudflared в простое почти не
consume CPU, worker во время чтений — 0.3% (замерено), и реальная сумма
худшего случая (web на пике + postgres + один синк) ≈ 1.0–1.2 ядра. Верхняя
граница квоты web подобрана так, чтобы postgres (пик 0.27 ядра при квоте 0.30,
то есть 90% — близко к потолку) не оказался отрезанным от web.

**Чего замер НЕ доказал.** Критерий «CPU < 90% своей квоты» на прогоне B
провален: web держится на 103% квоты весь прогон, то есть на 1 vCPU web всё
ещё троттлится и запаса по CPU нет. Пользовательский критерий p95 ≤ 500 мс при
этом проходит с запасом (405 мс). Честная формулировка: профиль 1/1 проходит
критерий задержки на синтетической нагрузке 4×1000 запросов, но не имеет
запаса по CPU, если такой поток сохранится. На документированном профиле §88
(20–30 активных учителей, разовые открытия дашборда) этот поток не
возникает; на синхронном всплеске «все открыли дашборд сразу» 1 vCPU даёт
очередь в несколько секунд.

Это самое сильное из имеющихся свидетельств в пользу 2 vCPU / 2 ГБ: даже после
перебалансировки квот на одном ядре web остаётся ограниченным, а postgres
стоит на 90% своей квоты.

**Наблюдение по RAM.** `worker` — самое плотное измерение: пик 83M при лимите
160M (52%). Запас меньше, чем у остальных (web 93/256, postgres 35/288). Если
на реальном VPS синк учителя с большим ростером поднимет worker выше ~120M,
лимит нужно поднять — и следить за этим стоит первым, потому что остальные два
сервиса используют треть лимита.

**Что осталось неизменным и почему.** Пул БД `3 + 2` не увеличивался: в
замере пик 7 соединений при бюджете 10, лимитов pool не достигнуто, а на
CPU-bound коробке дополнительные соединения не дают пропускной способности.
`SYNC_MAX_CONCURRENT_USERS=1`, `SYNC_WORKERS=2`, интервал 30 мин и
`SYNC_STARTUP_STAGGER_SECONDS=600` не трогались: с квотой worker 0.15 фоновый
синк становится медленнее, но не ломается, а именно стартовый stagger спасает
от худшего сценария.

### 2.3 Manual sync — queued, а не inline (DDoS §9)

`POST /api/sync` в hosted-режиме больше не выполняет Classroom-фан-аут
внутри HTTP-запроса:

- уже идёт синк этого пользователя → **409**;
- ручной синк внутри per-user cooldown → **429 + Retry-After**;
- иначе `sync_store.request_sync(user_id)` (флаг `sync_requested`) и
  немедленный ответ `{"ok": true, "queued": true, "status": "queued"}`.

Работу делает worker/планировщик. Desktop-ветка сохраняет inline-контракт
(и 503 `SERVER_BUSY` при исчерпании интерактивного пула) — это
зафиксировано в `SyncResult.queued/status` и в тестах.
Frontend после `queued` держит спиннер и опрашивает `/api/status`, пока
`syncing` не станет `false`; после terminal status он перечитывает cache без
перезагрузки страницы.

Отклонение от DDoS-дока: там предполагалась отдельная таблица `sync_jobs` и
`enqueue_user_sync`; мы переиспользовали существующую `sync_status` с
флагом `sync_requested` и claim-семантикой (ADR-0023), потому что она уже
даёт дедупликацию между воркерами и не требует второй очереди.


### 2.4 Cloudflare, firewall, Turnstile (DDoS §2/§3/§5/§18–§20)

- домен на Cloudflare nameservers, Zoho MX/TXT сохраняются;
- Tunnel публикует `monkstonecor.pp.ua → http://caddy:80`; публичного A на
  IP VPS нет, лишние `www/ftp/dev/api/staging` проверяются и не создаются;
- inbound на VPS: только SSH (по ключам), 80/443/5432/8000 закрыты;
- managed DDoS-правила Free включены; грубые edge-лимиты на
  `/api/auth/login*` и `/api/sync` — опция, авторитет по квотам остаётся у
  бэкенда (per-user cooldown + бакеты);
- **Turnstile реализован и env-gated** (DDoS §17, stage-10 дополнение):
  `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY` в `.env`; пустые = выключено
  (дефолт, dev/тесты не ходят в Cloudflare). При включении: `GET
  /api/auth/turnstile` сообщает публичный site key, виджет рендерится на
  экране входа, `POST /api/auth/login/start` проверяет токен на
  `siteverify` fail-closed, `GET /api/auth/login` отправляет браузер на
  `/?challenge=required` вместо обхода, CSP (только при включённом site key)
  добавляет `challenges.cloudflare.com` в `script-src`/`frame-src`,
  `/login/start` делит login-бакет rate-limit'а, отказы считаются в
  `metrics` (`turnstile_rejected/accepted`). Secret key — только env.

### 2.5 Client IP

`proxy.client_ip()`: TCP-пир по умолчанию; `CF-Connecting-IP` (или левый
`X-Forwarded-For`) — **только** если пир в `GC_DASHBOARD_TRUSTED_PROXIES`.
Доверять CF-заголовку без проверки пира нельзя: при прямом доступе к origin
любой подставил бы себе IP и обошёл бакет. В Compose доверенный пир — сеть
`internal` (Caddy/cloudflared).

### 2.6 Health / readiness (§58, DDoS §24)

- `GET /api/health` — публичный, `{"ok": true}`, без БД и секретов;
- `GET /api/ready` — публичный, `SELECT 1`, `200 {"ok": true, "db": "up"}`
  или `503 {"ok": false, "db": "down"}`; ловит только `SQLAlchemyError`,
  детали не отдаются; используется healthcheck'ом контейнера `web`.

### 2.7 Бэкапы (§57, DDoS §26)

`tools/backup_postgres.sh dump|restore|list`: `pg_dump --format=custom`,
rolling retention (7), restore останавливает `web`/`worker`, затем
`alembic upgrade head` и старт. Вместе с БД бэкапится `.env` (Fernet-ключ,
Google web client secret, tunnel token) — отдельно и зашифрованно; дампы
никогда не попадают в Git. Первую проверку `alembic upgrade head` на живой
PostgreSQL (отложенную с этапов 3/5/9) делает деплой.

### 2.8 Зависимости и гигиена (§72/§73/§77/§78)

- образ ставит `backend/requirements-prod.txt` (точные версии), dev-файл
  остаётся диапазонным; `npm ci` по закоммиченному `package-lock.json`;
- `.dockerignore` исключает `.env`, `credentials.json`,
  `embedded_secrets.py`, `data/`, `*.db`, `dist/`, `node_modules`, `build/`;
- `.gitignore` дополнен `backups/`, `*.dump`, явным `!.env.example`;
- роли контейнеров: non-root `app`, никаких секретов в слоях и `ENV`.

## 3. Соответствие §80 (ADR-история)

| §80 пункт | Где решён |
| --- | --- |
| 1. Hosted deployment из кода в браузере | ADR-0020/0021/0025 |
| 2. PostgreSQL вместо SQLite | ADR-0021 |
| 3. Web OAuth вместо loopback | ADR-0020 |
| 4. User identity и sessions | ADR-0020/0022 |
| 5. User isolation данных | ADR-0022 + этап 3 |
| 6. Per-user sync | ADR-0023 |
| 7. Docker/Caddy/деплой | **этот ADR** |
| 8. Rate limits/capacity | ADR-0027 + этот ADR (§2.2/2.4) |

## 4. Последствия

- Прод держится на одном VPS; горизонтального масштабирования нет — это
  осознанный стартовый тир, апгрейд вертикальный.
- In-memory rate-limit бакеты «на реплику»: при переходе на несколько web-
  процессов лимиты нужно выносить в общее хранилище (ADR-0027 §7).
- `queued`-синк означает, что UI не получает результат синка в ответе на
  POST; источник правды — `sync_status` в `/api/status`.
- Cloudflare Tunnel снимает необходимость публичных портов, но добавляет
  зависимость от CF: при недоступности CF сервис недоступен снаружи.
- HSTS включён в `.env.example` (`31536000`, только по https); при HSTS на
  самом edge значение выставляется в 0 во избежание дублей.
- Turnstile остаётся выключенным, пока в `.env` пустые ключи, — включение
  не требует правок кода, только env и перезапуск контейнеров.

## 5. Ссылки

- `Dockerfile`, `compose.yml`, `Caddyfile`, `.dockerignore`,
  `backend/requirements-prod.txt`, `tools/backup_postgres.sh`;
- `docs/DEPLOYMENT_CHECKLIST.md` — пошаговый порядок выката (DDoS §K);
- `docs/migration/audits/HOSTING_MIGRATION_STAGE10.md` — результат этапа.
