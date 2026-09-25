# Этап 9 — Rate Limits and Capacity Planning: результат

Реализация этапа 9 миграции на хостинг
(`Rate Limits and Capacity Planning Part 1 num in query 9.md`, §39–§46;
`Part 2`, §59–§62, §66, §68; `Part 3`, §70; `Part 4`, §88). Опорные
документы: аудит `HOSTING_MIGRATION_AUDIT.md`, результаты этапов 2–8
(`HOSTING_MIGRATION_STAGE2.md`–`HOSTING_MIGRATION_STAGE8.md`), решение
`docs/adr/adr-0027-rate-limits-capacity-retention.md`.

Дата: 2026-09-24. Все разделы промпта этапа 9 реализованы.

## 1. Что сделано (по пунктам промпта)

| Пункт | Требование | Реализация |
| --- | --- | --- |
| §39 | Rate limits на логин/callback/синк/очистку кэша; запрет неограниченного вызова Google | `rate_limit.RateLimiter` (token bucket, clock-инжектируемый) в `app.state`; hosted-middleware `throttle_abuse_surfaces`: логин 30/мин/IP, `POST /api/sync` 60/мин/IP, `DELETE /api/cache`+`/api/me/cache` 10/мин/IP → 429 + `Retry-After`; отклонённые callback'и — 20/мин/IP (успешные не считаются, школьный NAT не страдает); IP из `X-Forwarded-For` только от trusted proxy (`proxy.client_ip`); ручной синк дополнительно с per-user cooldown (`SYNC_MANUAL_COOLDOWN_SECONDS=60`) → 429, планировщик cooldown не проходит; desktop-путь не тронут |
| §40 | Не трактовать 16 воркеров как глобально-безопасных; per-user throttling + global concurrency | `SYNC_MAX_WORKERS` дефолт **16 → 4**, `SYNC_MAX_CONCURRENT_USERS=2` → бюджет 4×2=8 потоков; глобальный предел интерактивных синков (503) — со этапа 6; per-user пул и claim в БД остаются; env-кнопки с комментарием, когда их поднимать |
| §40/§88 | Считать `users × requests × concurrent` | `backend/capacity.py`: `estimate_requests_per_minute/second`, `sync_thread_budget`, `capacity_report` — 1000 юзеров + 25 учителей / 10 мин ≈ 600 req/min ≈ 10 QPS; оценка — код с тестами, не проза |
| §41 | invalid_grant → needs_reauth только для этого пользователя, без вечных рефрешей и глобального разлогина | `google_credentials.refresh_google_credentials`: `invalid_grant` удаляет **только** строку `oauth_tokens` этого пользователя (транзиентные ошибки — нет); 401 посреди синка (`sync_service`) → `delete_google_credentials(только этот)` + `mark_sync_needs_reauth`; сессии других пользователей и их гранты не затрагиваются (тесты) |
| §42 | Логи в stdout/stderr, без токенов/секретов/трейсов в браузере | `main.py`/`sync_worker.py` в hosted пишут в stdout; новый `access_log.RedactSecretsFilter` (пары `access_token=…`/`Bearer …`, `ya29.…`/`glpat-`/`gho_`, структурированные args) ставится на логи приложения, идемпотентно; query-редакция access-log — этап 8; `_public_error` (§59) возвращает короткие фразы, трейс только в лог |
| §43 | Ревью полей на минимизацию | Новых чувствительных полей не добавлено; scope не расширялись; email ростера по-прежнему опционален; удаление аккаунта убирает ростер/оценки этого пользователя каскадом; публичных API без сессии/скоупа нет (гейт + IDOR-тесты этапов 4/6) |
| §44 | Retention и удаление (сессии, токены, кэш, sync-состояние) только у этого пользователя; нет глобального destructive clear | новый `maintenance.py`: `purge_expired` (просроченные/отозванные сессии + истёкшие OAuth-попытки, sweep в воркере каждые `RETENTION_SWEEP_SECONDS=3600`), `disconnect_google` (грант вниз, аккаунт/сессии/кэш остаются), `delete_user_data` (сессии, токены, sync-состояние, весь кэш по каскаду, `users`-строка — всё с его id); новые ручки `DELETE /api/me` (hosted-only, иначе 400 с подсказкой), `DELETE /api/me/google`; обе требуют `confirm=true` |
| §45 | Короткие транзакции, ни одной открытой сессии через сетевой вызов Google, сессии не между потоками, пул | `_do_sync` разложен на фазы: claim+креденшелы (сессия №1) → **закрыта** → фетч к Google без открытого соединения (тест: `pool.checkedout()==0`) → запись (сессия №2, коммит на курс, purge/mark); воркеры не делят Session; PostgreSQL-пул `pool_size=5`, `max_overflow=5`, `pool_timeout=30`, `pool_recycle=1800`, `pool_pre_ping` |
| §46 | Конкурентные правила (2 вкладки, 2 callback, refresh, 2 клика, ручной+фоновый, разные юзеры, одинаковый course id) | Таблица в ADR-0027 §5: каждый сценарий закрыт существующим механизмом (сессии, per-attempt state, per-user refresh-лок, claim+лок → 409, cooldown → 429, независимые per-user джобы, user-scoped PK) и покрыт тестами этапов 2–9 |
| §59 | Без сырых исключений в публичных ответах, статусы 401/403/404/409/429/502–503 | `_public_error` санитизирует (тест с `client_secret=…` внутри исключения); 409 — «синк уже идёт», 503 — «сервер занят», **новый 429** — cooldown/лимиты с `Retry-After`; 401/403/404 — из этапов 4/6 |
| §60 | Метрики: активные юзеры, логины, длительность/исходы синка, 429/5xx Classroom, крахи воркера, auth-отказы | новый `metrics.py` (счётчики по именам событий, без ПДн) + периодическая строка `metrics[worker] …` из цикла планировщика; `RequestStats` получил `quota_errors`/`server_errors` и `snapshot()`, они пишутся в каждую строку успеха/падения синка (`google_requests=… quota_errors=… server_errors=… duration=…`); `metrics` пополняют login/logout/session-reject/sync-исходы/крах джобы/retention-sweep |
| §61 | Явно решить: авторитет, кэш, missed sync, stale-данные, TTL, удаления, archived | ADR-0027 §6: авторитет — Google, PostgreSQL — кэш; после неудачного синка кэш остаётся, `last_success_at` сохраняется, `sync_status=error` + санитизированная ошибка (тест §61); age всегда на виду в `/api/status` (не выдаём stale за current); TTL-сгорания кэша нет — сверка следующим синком; удаления — зеркальный purge; archived скрыт (этап 6) |
| §62 | Не делить in-memory/будущий Redis-кэш по голому Google id | Тест: `_profile_cache` ключуется локальным `user_id` (два пользователя — два значения, повторный запрос из кэша); таблицы — `(user_id, …)` с этапа 3; рейт-лимиты ключуются `(surface, ip)`/пользователем; правило «Google id не может быть голым ключом» — в ADR-0027 §6 |
| §66 | `DELETE /api/cache?confirm=true` только для вызывающего + рассмотреть переименование | Скоуп был ещё с этапа 3/4; добавлен явный алиас **`DELETE /api/me/cache`** (тот же скоуп/`confirm`, оба за гейтом и rate-limit'ом); глобального варианта нет |
| §68 | Индекс по реальным паттернам, без слепых списков | Ревизия: 6 из 7 кандидатов уже покрыты PK с префиксом `user_id` и `ix_coursework_user_course`/`ix_cw_submission_user_course`; пробел — `sessions(user_id, expires_at)` → Alembic **0003** (создаёт составной, падает избыточный `ix_sessions_user_id`); upgrade/downgrade `--sql` для postgresql прогнаны, `alembic check` на чистой БД — «No new upgrade operations detected»; тест фиксирует состав индексов и правило «индекс кэш-таблицы начинается с user_id» (исключения задокументированы) |
| §70 | Не сломать timezone-семантику | Семантика не менялась и закреплена тестом: все `_utcnow()`/`_now()` возвращают naive UTC, сравнения — наивная арифметика (DST к stored-значениям не применяется), due-даты Classroom остаются naive-локальными (ADR-0004), рендер в локальной зоне — фронт (`dates.toLocalDate`, этап 7); миграция таймзон не требуется |
| §88 | Capacity-план на 1000 юзеров: потоки, bounded sync, стагтер, оценка до релиза, teacher-нагрузка, индексы, без лишней инфры, acceptance criteria | `capacity.py`-оценка (student-shape 5 req, teacher-shape +40 req), стагтер/батч/backoff — этап 5, bounded пул 8 потоков, малый DB-пул под 1 vCPU/1 GB, без Redis/Celery/WebSockets/K8s; web отдаёт UI из PostgreSQL (не фан-аут в Google на каждый клик); критерии приёмки (load-test RAM/CPU/latency/queue depth/сверка `google_requests`) и сигналы масштабирования (вертикальный шаг 1→2 vCPU первым) — в ADR-0027 §7, прогон — **этап 10** |

## 2. Файлы

Добавлено:

- `backend/rate_limit.py` — token-bucket лимитер (§39): внедряемый clock,
  registry на экземпляр приложения, `reset()` для тестов.
- `backend/maintenance.py` — retention и удаление (§44): `purge_expired`,
  `revoke_sessions`, `disconnect_google`, `delete_user_data`.
- `backend/metrics.py` — операционные счётчики (§60): `record/snapshot/
  log_snapshot/reset`, именованные события без ПДн.
- `backend/capacity.py` — арифметика capacity (§40/§88):
  `estimate_requests_per_minute/second`, `sync_thread_budget`,
  `peak_requests_per_minute`, `capacity_report`.
- `migrations/versions/0003_stage9_session_index.py` (§68).
- `tests/test_stage9_limits_capacity.py` — 35 тестов.
- `docs/adr/adr-0027-rate-limits-capacity-retention.md`.

Изменено:

- `backend/config.py` — `RATE_LIMIT_LOGIN_PER_MINUTE`,
  `RATE_LIMIT_CALLBACK_FAILURES_PER_MINUTE`, `RATE_LIMIT_SYNC_PER_MINUTE`,
  `RATE_LIMIT_CACHE_CLEAR_PER_MINUTE`, `SYNC_MANUAL_COOLDOWN_SECONDS`,
  `RETENTION_SWEEP_SECONDS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`;
  `SYNC_MAX_WORKERS` 16 → 4.
- `backend/main.py` — `app.state.rate_limiter`, middleware
  `throttle_abuse_surfaces` (hosted), `install_secret_redaction()` в
  lifespan hosted.
- `backend/proxy.py` — `client_ip()` (X-Forwarded-For только от trusted
  proxy).
- `backend/api.py` — cooldown в `run_sync` (429 + Retry-After);
  `DELETE /api/me/cache`; `DELETE /api/me/google`; `DELETE /api/me`
  (hosted-only).
- `backend/hosted_auth.py` — счётчики login/login-fail/logout/session-reject;
  отказ в callback считается и попадает в bucket лимита.
- `backend/google_credentials.py` — `invalid_grant` → удаление только
  своего `oauth_tokens` (`_is_invalid_grant`).
- `backend/sync_service.py` — фазовая структура `_do_sync`/`_write_sync_results`
  (§45), 401-фетч → `needs_reauth` + удаление своего гранта (§41),
  `quota_errors/server_errors` в логах (§60), счётчики `metrics`.
- `backend/classroom_api.py` — `RequestStats.quota_errors/server_errors/
  snapshot`, классификация HttpError (429/403-quota/5xx) в `_execute`.
- `backend/sync_scheduler.py` — `run_maintenance()` (retention sweep +
  `metrics.log_snapshot`) в цикле скана; счётчик крахов джоба.
- `backend/sync_worker.py` — stdout-лог + secret-фильтр; `--once` делает
  sweep перед сканом.
- `backend/database.py` — PostgreSQL-пул `5+5`, `pool_timeout`,
  `pool_recycle`.
- `backend/access_log.py` — `RedactSecretsFilter`,
  `redact_secrets_in_text`, `install_secret_redaction()`.
- `backend/models_auth.py` — составной индекс `ix_sessions_user_expires`,
  удалён одноколоночный `ix_sessions_user_id`.
- `ruff.toml` — first-party: `capacity`, `maintenance`, `metrics`,
  `rate_limit`.
- `tests/conftest.py` — герметичность stage-9 env-кнопок.
- `.env.example`, `README.md`, `docs/adr/README.md` — новые переменные и
  раздел «Rate limits, capacity и retention».
- `frontend/openapi.json`, `frontend/src/api-schema.d.ts` — перегенерированы
  (`tools/dump_openapi.py` + `npm run gen:api:file`); `tsc`/eslint проходят.

## 3. Закрытые пункты аудита

| Аудит | Было | Стало |
| --- | --- | --- |
| C4 | бюджет синка рассчитан на 1 пользователя (16 воркеров) | пересчёт: 4×2=8 потоков, `capacity.py`, env-комментарии и гейт роста по счётчикам |
| §39 аудита (новый) | публичные лимиты отсутствовали | 4 поверхности с IP-бакетами + per-user cooldown; desktop без лимитов |
| §41 (новый) | смерть гранта вела к вечным рефрешам | `invalid_grant`/401 → удаление своего гранта + `needs_reauth`, остальные не тронуты |
| §42 (новый) | hosted без явной политики логов | stdout + redaction-фильтр; query-редакция (этап 8) продолжает работать |
| §44 (новый) | не было retention и «удалить аккаунт» | sweep мёртвых сессий/попыток; `DELETE /api/me`, `/api/me/google`, `/api/me/cache` — всё per-user |
| §45 (новый) | сессия держалась через сетевой фетч | фазовые короткие транзакции, пул 5+5 с recycle |
| §46/§59/§60 (новые) | частично закрыты этапами 2–6 | сводка + 429, счётчики quota/5xx/login/sync, периодическая строка метрик |
| §61/§62/§66/§68/§70 (новые) | частично закрыты этапами 3–7 | явные решения в ADR-0027, тесты, Alembic 0003, алиас `/api/me/cache` |

## 4. Тесты (197 всего, все зелёные; было 162)

Новые (`tests/test_stage9_limits_capacity.py`, 35):

- §39: bucket наполняется/сбрасывается по времени, смена capacity даёт
  свежий bucket; hosted `POST /api/sync` → 429 + Retry-After на 3-м
  запросе, desktop не лимитируется; логин-редирект лимитируется;
  отклонённые callback'и упираются в лимит (429-marker), cooldown
  возвращает 429 и истекает, cooldown — per-user;
- §41: `invalid_grant` удаляет только свой токен (грант B жив),
  транзиентная ошибка грант не трогает, 401-фетч → `needs_reauth` +
  удаление гранта A и живой грант B;
- §42: log-запись с `access_token=`/cookie от redact'ится, операционные
  поля не трогаются, фильтр ставится идемпотентно;
- §44/§66: sweep убирает ровно мёртвые сессии/попытки; disconnect
  сохраняет аккаунт/сессию/кэш и `last_success_at`; удаление аккаунта
  вычищает все свои таблицы и не трогает соседа; `DELETE /api/me` 400 без
  confirm, после — 200, cookie падает, сосед жив, следующий запрос 401;
  desktop на `/api/me` → 400; `/api/me/google` требует confirm, сессия
  переживает disconnect; `/api/me/cache` чистит только вызывающего;
- §45: во время фетча в пуле 0 открытых соединений; после фетча claim
  корректно закрыт (`sync_status=error` в отдельной сессии);
- §59/§60: `_public_error` для 401/403/429/500 и не-HTTP исключения —
  короткие фразы без текста исключения; счётчики сессий/логинов двигаются
  и не содержат ПДн; `RequestStats` различает 429/5xx; строка
  `metrics[…]` логируется;
- §61: упавший синк сохраняет кэш, возраст (`last_success_at`) и санитизированную
  ошибку; §62: кэш профиля ключуется локальным id и кэшируется per-user;
- §68: состав индексов сессий/coursework/submissions + правило
  «первый столбец — user_id» с исключениями; PK-префикс `user_id`;
- §70: все `_utcnow()`/`_now()` naive UTC, наивная арифметика due-сравнений;
- §88: дефолты консервативны (workers ≤ 8, concurrent ≤ 4, пул ≤ 10,
  cooldown > 0); 1000×5 + 25×40 = 600 req/min, ×2 при укорочении
  интервала, `interval=0` → ValueError; thread budget = произведение
  двух лимитов.

Обновлены: `tests/conftest.py` (герметичность stage-9 env).

## 5. Проверки

- `pytest`: 197 passed (было 162).
- `ruff check` / `ruff format --check` (backend, tests, migrations): чисто.
- `pyright` (`pyrightconfig.json`): 0 errors.
- Alembic: `upgrade 0002:0003 --sql` и `downgrade 0003:0002 --sql` на
  диалекте postgresql компилируются; полный `upgrade head` на чистой БД;
  `alembic check` — «No new upgrade operations detected» (миграция ==
  метаданным). Против живого PostgreSQL, как и на этапах 3/5, не
  прогонялось — первая прод-проверка в этапе 10.
- `npm run lint` (eslint + tsc): чисто после перегенерации api-schema;
  `npx vitest run`: 51 passed.
- Секретов в отслеживаемых исходниках нет; новых env-переменных — только
  имена в `.env.example` (плейсхолдеры); `gitleaks` CLI в среде
  отсутствует — прогон остаётся за этапом 10.

## 6. Что осталось за пределами этапа 9 (и почему)

- **Этап 10 (деплой):** load-test на живом PostgreSQL с критериями §88
  (RAM/CPU/latency/HTTP-ошибки/`google_requests`/глубина очереди/длительность
  синка), сверка `capacity.py`-оценки с фактическими `quota_errors`,
  первый `alembic upgrade head` (включая 0003) на прод-БД, gitleaks в
  пайплайне, README-смоук много-пользовательского сценария.
- **Включение HSTS и браузерный CSP-смоук** — после подтверждения HTTPS
  (отложено из этапа 8).
- **Смоук собранного exe** — за владельцем (desktop-код этапа 9 менялся
  только ленивыми импортами/счётчиками; все desktop-тесты зелёные).
- Ограничение buckets «на реплику» — пересмотреть при выходе на несколько
  реплик (ADR-0027 §7); сейчас поддерживаемая архитектура — одна
  web-реплика + один воркер (этапы 5/10).



