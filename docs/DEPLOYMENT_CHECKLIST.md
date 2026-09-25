# Deployment checklist — hosted Google Class Help

Пошаговый порядок выката на VPS (миграция этап 10, ADR-0028; порядок — по
§K `GoogleClassHelp_DDoS_Security_Code_Changes.md`). Целевой хост: 1 vCPU /
1 GB, домен `monkstonecor.pp.ua`, Cloudflare Free + Tunnel.

Обозначения: **[VPS]** — на сервере, **[CF]** — в Cloudflare Dashboard,
**[PC]** — на локальной машине.

## 0. Предусловия

- [ ] Репозиторий на ветке с этапами 1–10; `pytest`, `ruff`, `pyright`,
      `npm run lint`, `npx vitest run` зелёные локально.
- [ ] Создан **отдельный** Google OAuth-клиент типа *Web application* с
      redirect URI `https://monkstonecor.pp.ua/api/auth/callback`.
- [ ] Сгенерирован Fernet-ключ: `python tools/generate_hosted_secrets.py`.
- [ ] Придуман длинный `POSTGRES_PASSWORD`.

## 1. Cloudflare (DDoS §2/§3/§18–§20)

- [ ] **[CF]** Добавить домен, сменить NS у регистратора; Zoho MX/TXT
      сохранить.
- [ ] **[CF]** Managed DDoS-правила оставить включёнными.
- [ ] **[CF]** Networking → Tunnels → Create Tunnel → published application:
      hostname `monkstonecor.pp.ua` → service `http://caddy:80`; токен
      скопировать (уйдёт в `.env` как `CLOUDFLARE_TUNNEL_TOKEN`).
- [ ] **[CF]** Опционально: грубые rate-limit правила на
      `/api/auth/login*` и `/api/sync` (бэкенд остаётся авторитетом).
- [ ] **[CF]** Проверить DNS: нет `www/ftp/dev/api/staging`, указывающих на
      IP VPS.

## 2. VPS и firewall (DDoS §5)

- [ ] **[VPS]** Установить Docker Engine + Compose plugin.
- [ ] **[VPS]** Firewall: inbound только SSH; `80/443/5432/8000` закрыты
      (Tunnel исходящий).
- [ ] **[VPS]** SSH-ключи; после проверки входа отключить пароли
      (`PasswordAuthentication no`).
- [ ] **[VPS]** `git clone <repo> /opt/google_class_help && cd /opt/google_class_help`.

## 3. Конфигурация

- [ ] **[VPS]** `cp .env.example .env`, заполнить:
      `APP_BASE_URL`, `GOOGLE_CLIENT_ID/SECRET`,
      `GOOGLE_REDIRECT_URI`, `GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY`,
      `POSTGRES_PASSWORD`, `CLOUDFLARE_TUNNEL_TOKEN`, `BACKUP_DIR`.
- [ ] **[VPS]** `GC_DASHBOARD_TRUSTED_PROXIES` — CIDR docker-сети
      (`docker network inspect google_class_help_internal`), иначе
      forwarded-заголовки не будут trusted.
- [ ] **[VPS]** `GC_DASHBOARD_COOKIE_HOST_PREFIX=1` (Secure + Path=/ уже
      выполнены в проде). `GC_DASHBOARD_HSTS_MAX_AGE=31536000` — HSTS включён;
      `0`, если HSTS настраивает сам Cloudflare edge.
- [ ] **[VPS, опционально]** Turnstile: создать виджет в Cloudflare Dashboard
      → Turnstile и заполнить `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY`
      (пустые = проверка выключена).
- [ ] **[VPS]** Проверить: `docker compose config --quiet`.
- [ ] **[VPS]** `.env` не отслеживается Git: `git status --short` чист.

## 4. Сборка и первый запуск

- [ ] **[VPS]** `docker compose build`
- [ ] **[VPS]** `docker compose up -d postgres` → дождаться `healthy`
      (`docker compose ps`).
- [ ] **[VPS]** Миграции (первый прогон Alembic на живой PostgreSQL):
      `docker compose run --rm --workdir /app web alembic -c /app/alembic.ini upgrade head`
- [ ] **[VPS]** `docker compose up -d web worker caddy cloudflared`
- [ ] **[VPS]** `docker compose ps` — все сервисы `running`/`healthy`,
      `docker stats --no-stream` — RAM/CPU в лимитах.

## 5. Проверки после выката

- [ ] **[PC]** `curl -fsS https://monkstonecor.pp.ua/api/health` → `{"ok":true}`
- [ ] **[PC]** `curl -fsS https://monkstonecor.pp.ua/api/ready` → `db: up`
- [ ] **[PC]** HTTPS-сертификат валиден; HTTP→HTTPS (на стороне CF).
- [ ] **[PC]** `curl -sI https://monkstonecor.pp.ua/api/health` содержит
      `strict-transport-security: max-age=31536000; includeSubDomains` (HSTS).
- [ ] **[PC, если Turnstile включён]** экран входа показывает виджет,
      `GET /api/auth/login` ведёт на SPA (`/?challenge=required`), а не
      мимо проверки; `GET /api/auth/turnstile` → `enabled: true`.
- [ ] **[PC]** Вход через Google, `GET /api/me` отдаёт свой профиль.
- [ ] **[PC]** Два разных Google-аккаунта: не видят данные друг друга;
      одинаковый Google course id у обоих не смешивается.
- [ ] **[PC]** Teacher-сценарий: у аккаунта teacher-роль в одном курсе и
      student-роль в другом; `/students` недоступен на студенческом курсе.
- [ ] **[PC]** `POST /api/sync` → `{"queued": true}`; в UI спиннер сразу после
      ответа и до terminal `syncing=false`; данные обновляются автоматически;
      повторный клик → 429 с `Retry-After`; при идущем синке → 409.
- [ ] **[PC]** `DELETE /api/me/cache?confirm=true` чистит только свой кэш.
- [ ] **[VPS]** Postgres/8000 недоступны снаружи (проверить с другого
      хоста: `nc -vz <IP> 5432` / `8000` — отказ).
- [ ] **[VPS]** Логи без секретов: `docker compose logs --tail=200 web`
      (нет `access_token`, `refresh_token`, `client_secret`).

## 6. Бэкапы (DDoS §26, ADR-0028 §2.7)

- [ ] **[VPS]** `./tools/backup_postgres.sh dump` → файл в `backups/`.
- [ ] **[VPS]** cron: `30 3 * * * cd /opt/google_class_help && ./tools/backup_postgres.sh dump >> logs/backup.log 2>&1`
- [ ] **[VPS]** Пробный restore на тестовой БД: `dump → drop → restore →
      alembic upgrade head → health/ready`.
- [ ] **[VPS]** `.env` сохранён в защищённом месте (менеджер паролей);
      зашифрованная копия дампа периодически увозится с VPS.
- [ ] **[VPS]** Дампы не в Git: `git status --short` и `git check-ignore`.

## 7. Осознанные выключатели

- **Turnstile (DDoS §17)** реализован и env-gated: заполните
  `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY` (Cloudflare Dashboard →
  Turnstile), когда решите включить проверку; пустые ключи = поведение
  как раньше. При включении: виджет на экране входа,
  `POST /api/auth/login/start` проверяет токен на siteverify (fail-closed),
  прямой `GET /api/auth/login` больше не обходит проверку, CSP получает
  origin виджета (script-src/frame-src).
- **HSTS включён** по умолчанию в `.env.example`
  (`GC_DASHBOARD_HSTS_MAX_AGE=31536000`); заголовок уходит только по https.
  Если HSTS настраивает сам Cloudflare edge — поставьте `0`.
- бэкап-копия «навсегда» — только rolling retention + offsite-копия.

## 8. Load test (§88)

Критерии приёмки (ADR-0027 §7, ADR-0028 §2.2): на целевом VPS под
нормальной нагрузкой — без 5xx, p95 в пределах порога, RAM/CPU в лимитах
compose, глубина очереди синка не растёт, `quota_errors` в логе не
увеличивается.

- [ ] **[VPS]** Параллельно с нагрузкой: `docker stats --no-stream` —
      `web` ≤ 256M, `worker` ≤ 384M, `postgres` ≤ 384M, CPU не в 100%.
- [ ] **[PC]** Без аутентификации (пусть идёт с Cloudflare):
  `python tools/load_test.py --base-url https://monkstonecor.pp.ua --path /api/health --path /api/ready --requests 1000 --concurrency 30`
  → PASS (p95 ≤ 500 ms, 0 5xx).
- [ ] **[PC]** Аутентифицированная серия (cookie из реального входа):
  `python tools/load_test.py --base-url https://monkstonecor.pp.ua --path /api/status --path /api/courses --cookie gch_session=<value> --requests 500 --concurrency 20`
  → PASS.
- [ ] **[VPS]** После прогона: в логах воркера нет новых `quota_errors`,
      `docker compose logs worker --tail=100` — без крахов, `metrics[…]`
      строка показывает разумные счётчики.
- [ ] Локальная самопроверка инструмента уже выполнена (см. аудит этапа 10):
  300 запросов @ 10 против dev-сервера → PASS, p95 ≈ 44 ms.

## 9. Откат

- [ ] `docker compose down` (volume `pgdata` сохраняется).
- [ ] Плохой релиз: `git checkout <prev> && docker compose build && up -d`;
      миграции — `alembic downgrade <rev>` только по ADR-0021.
- [ ] Потеря данных: `./tools/backup_postgres.sh restore backups/<file>.dump`.
