# Architecture Decision Records

Записи архитектурных решений проекта **Local Google Classroom Dashboard**.

Формат: короткие ADR (контекст → решение → последствия). Статусы: Accepted, если
не указано иное. Суперсе́денные записи не удаляются.

| Номер | Название | Статус |
| --- | --- | --- |
| [ADR-0001](adr-0001-layered-local-architecture.md) | Слоистая локальная архитектура без облака | Accepted |
| [ADR-0002](adr-0002-minimal-oauth-scopes.md) | Минимальный набор OAuth scopes | Accepted |
| [ADR-0003](adr-0003-sqlite-cache-and-sync.md) | SQLite-кэш и стратегия синхронизации | Accepted |
| [ADR-0004](adr-0004-derived-fields-server-side.md) | Производные поля (статус, приоритет) считаются на бэкенде | Accepted |
| [ADR-0005](adr-0005-frontend-stack.md) | Фронтенд: React + TS + Vite и CSS-токены вместо Tailwind | Accepted |
| [ADR-0006](adr-0006-settings-in-localstorage.md) | Пользовательские настройки хранятся в localStorage | Accepted |
| [ADR-0007](adr-0007-notification-center.md) | Центр уведомлений вместо системных нотификаций | Accepted |
| [ADR-0008](adr-0008-average-grade-in-percent.md) | Средний балл считается в процентах | Accepted |
| [ADR-0009](adr-0009-calendar-client-side.md) | Календарные сетки строятся на клиенте | Accepted |
| [ADR-0010](adr-0010-student-sync-route.md) | Студенческий маршрут чтения заданий (submissions + point-get) | Accepted |
| [ADR-0011](adr-0011-i18n.md) | Мультиязычность en/uk/ru (типизированный i18n без зависимостей) | Accepted |
| [ADR-0012](adr-0012-client-side-global-search.md) | Глобальный поиск выполняется на клиенте (дропдаун поверх кэша) | Accepted |
| [ADR-0013](adr-0013-assignment-filter-panel.md) | Фильтры заданий: боковая панель, мультивыбор и сохранение между переходами | Accepted |
| [ADR-0014](adr-0014-parallel-staged-sync.md) | Стадийная параллельная синхронизация (общий пул на весь sync) | Accepted |
| [ADR-0015](adr-0015-background-sync-schedule.md) | Фоновая синхронизация — при старте, по расписанию и после входа | Accepted |
| [ADR-0016](adr-0016-production-nuitka-packaging.md) | Production-сборка — единый exe на Nuitka с встроенным фронтендом | Accepted |
| [ADR-0017](adr-0017-teacher-mode.md) | Teacher-режим — отдельный маршрут чтения курса | Accepted |
| [ADR-0018](adr-0018-single-instance-launcher.md) | Single-instance launcher — mutex, state-файл порта, трей и активация дашборда | Accepted |
| [ADR-0019](adr-0019-oauth-flow-owned-by-app.md) | OAuth-флоу во владении приложения — свой loopback-callback и единый HTTPS-транспорт | Accepted |
| [ADR-0020](adr-0020-hosted-web-oauth-and-sessions.md) | Хостед-режим — web OAuth, серверные сессии и шифрование токенов | Accepted |
| [ADR-0021](adr-0021-postgresql-alembic-user-scoped-schema.md) | PostgreSQL + Alembic и user-scoped схема кэша | Accepted |
| [ADR-0022](adr-0022-user-isolation-get-current-user.md) | User isolation — get_current_user и user-scoped Google-креденшелы | Accepted |
| [ADR-0023](adr-0023-per-user-sync-scheduler.md) | Per-user синхронизация — планировщик/воркер, `sync_status`, needs_reauth | Accepted |
| [ADR-0024](adr-0024-teacher-mode-api-surface.md) | Teacher-mode API surface — role gates, `/api/me`, identity shape и глобальный предел интерактивного синка | Accepted |
| [ADR-0025](adr-0025-frontend-config-production.md) | Production frontend и session boundary — env-Host/CORS/trusted proxy, cookie-флаги и `/data` | Accepted |
| [ADR-0026](adr-0026-desktop-hosted-coexistence-production-edge.md) | Desktop/hosted coexistence и production edge — разделение модулей, Option A, HTTPS/CSRF/headers, privacy/terms | Accepted |
| [ADR-0027](adr-0027-rate-limits-capacity-retention.md) | Rate limits, capacity и retention — токен-бакеты, бюджет синка 4×2, retention/удаление, короткие транзакции | Accepted |
| [ADR-0028](adr-0028-docker-caddy-cloudflare-deployment.md) | Docker/Compose/Caddy + Cloudflare Tunnel деплой — 1 vCPU/1 GB, queued manual sync, `/api/ready`, бэкапы | Accepted |
| [ADR-0029](adr-0029-public-landing-page.md) | Публичная посадочная страница вместо карточки входа, язык по браузеру | Accepted |
| [ADR-0030](adr-0030-sync-completion-toast.md) | Тосты о завершении синхронизации на sonner; триггер — серверная отметка `last_sync_finished_at` | Accepted |
| [ADR-0031](adr-0031-production-domain-and-generated-favicon.md) | Продуктовый домен `classroomhelp.pp.ua` и генерируемая иконка сайта (фавики в `frontend/public`, шаг иконки в `build.bat` перенесён до фронтенд-сборки) | Accepted |
| [ADR-0032](adr-0032-stuck-sync-restart.md) | Перезапуск зависшего синка: `?restart=true`, `abandon_claim` и fence-токен «проигравшего» запуска | Accepted |
| [ADR-0033](adr-0033-idempotent-cache-writes.md) | Идемпотентная запись кеша — `ON CONFLICT DO UPDATE` вместо get-then-add; fence переносится в per-course цикл записи | Accepted |
| [ADR-0034](adr-0034-document-language-follows-ui.md) | Язык документа следует за языком интерфейса: `<html lang>` устанавливает `SettingsProvider` (pre-paint — `prepaint-init.js`) | Accepted |
| [ADR-0035](adr-0035-feedback-tickets-and-administrators.md) | Тикеты обратной связи: домен с каскадом от `users.id`, allow-list администраторов из `ADMIN_EMAILS` (fail closed), ответ открывает решённый тикет, окончательное удаление, лимиты вложений 3×5 МБ / 10 МБ и подъём `Caddyfile` до 16 MB | Accepted (часть §2 заменена [ADR-0036](adr-0036-super-admin-and-admin-registry.md)) |
| [ADR-0036](adr-0036-super-admin-and-admin-registry.md) | Super Admin через `SUPER_ADMIN_EMAIL`, реестр администраторов в PostgreSQL, отдельная консоль `/admin` | Accepted |
| [ADR-0037](adr-0037-donation-qr-codes.md) | Поддержка проекта: QR-коды банков в `frontend/public/donate/`, один компонент `DonateCards` на лендинге и в настройках (карточка свёрнута), текст про деньги в i18n | Accepted (часть «две точки входа» заменена [ADR-0038](adr-0038-donation-settings-only.md)) |
| [ADR-0038](adr-0038-donation-settings-only.md) | Поддержка проекта спрашивается в настройках, а не на публичном лендинге | Accepted |
| [ADR-0039](adr-0039-layered-backend-packages.md) | Слоистые пакеты внутри `backend/`: `api/`, `core/`, `db/`, `google/`, `sync/`, `auth/`, `edge/`; `backend/` остаётся корнем `sys.path` ради Nuitka-сборки | Accepted |
| [ADR-0040](adr-0040-layered-frontend-slices.md) | Пять слоёв в `frontend/src`: `shared/`, `entities/`, `features/`, `widgets/`, `pages/`, `app/` вместо плоских `components/`/`lib/`/`context/` | Accepted |
| [ADR-0041](adr-0041-client-side-excel-export.md) | Клиентский экспорт курса в Excel: пресетная архитектура, ExcelJS, ноль строк бэкенда и ноль новых запросов | Accepted |
| [ADR-0042](adr-0042-grades-chart-dialog.md) | График динамики оценок: своя отрисовка SVG в `features/grades-chart/`, две оси, модалка, ноль зависимостей и ноль строк бэкенда | Accepted |
| [ADR-0043](adr-0043-teacher-matrix-grade-display.md) | Формат ячейки в таблице «Все ученики»: балл, балл из максимума, процент или всё вместе — переключатель в настройках | Accepted |
