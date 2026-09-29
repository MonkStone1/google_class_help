# Hosting Migration Audit (Stage 1)

Аудит репозитория перед миграцией на хостинг — результат этапа 1
(`docs/migration/Audit and Target Architecture num in query 1.md`).

Дата: 2026-09-18. Все ссылки на файлы даны по состоянию дерева на момент аудита.
Секреты в документ не выносятся; все упоминания конфигурации — имена
переменных окружения и файлов, никакой client_id/secret здесь нет.

---

## 1. Текущая архитектура (проверено по коду)

Приложение — **локальный десктоп-дашборд на одного пользователя**:

```text
Браузер (localhost)
   ↓
Vite dev server (:5173, dev) ИЛИ FastAPI + frontend/dist (production exe)
   ↓
FastAPI (backend/main.py)
   ├── auth.py            — desktop loopback OAuth (ADR-0019)
   ├── api.py             — /api/* ручки, читают SQLite
   ├── sync.py → sync_service.py / sync_store.py — синхронизация
   ├── background_sync.py — один глобальный цикл по расписанию
   └── classroom_api.py   — транспорт к Google Classroom
   ↓
SQLite (data/classroom.db) ← кэш на один аккаунт
   ↓
Google Classroom API (read-only)
```

Подтверждено по коду:

- **Один токен.** `config.py` определяет `TOKEN_FILE = DATA_DIR / "token.json"`;
  `auth.py::load_credentials / _save_credentials / logout / get_valid_credentials`
  работают ровно с этим одним файлом. Понятия «пользователь приложения» в коде нет.
- **Один профиль.** `api.py::_profile_cache` — кэш на 5 минут без ключа
  (просто кортеж «последнего» профиля всего процесса).
- **Один sync.** `sync_service.py::_SYNC_LOCK` — мьютекс всего процесса;
  `_do_sync()` берёт креденшелы через `auth.get_valid_credentials()` и
  синхронизирует единственный аккаунт.
- **Один фоновый цикл.** `background_sync.py`: глобальные `_stop`,
  `_scheduler`, `_runs` (ThreadPoolExecutor на 1 воркера), интервал
  `SYNC_INTERVAL_MINUTES` — расписание на весь процесс, а не на пользователя.
- **Desktop-обвязка.** `launcher.py`: single-instance mutex (named mutex
  Windows), tray-иконка, `webbrowser.open`, state-файл порта; бинд uvicorn
  строго на `127.0.0.1`.
- **Фронтенд.** `frontend/src/api.ts` использует `BASE = "/api"` (same-origin —
  это сохраняем), `DataContext.tsx` опрашивает `GET /api/auth/status`,
  `POST /api/auth/login|logout` возвращают `AuthStatus`. Никаких cookies,
  обработки 401 или выбора аккаунта фронтенд не знает.

### OAuth (auth.py, ADR-0019)

Consent-флоу принадлежит приложению: собственный loopback-callback-сервер
`_CallbackServer` на `http.server`, bind `127.0.0.1:<ephemeral>`, state
проверяется вручную, обмен кода — requests с fallback на httplib2.
Клиент-конфиг: `backend/credentials.json` (dev, git-ignored) →
`embedded_secrets.py` (build-time, base64, **не шифрование** — только чтобы
plaintext не попал в поставку). Это корректно для desktop-поставки, но
неприемлемо как механизм хранения секретов сервера.

### Что уже хорошо и сохраняется

- `BASE = "/api"` — same-origin, фронтенд никогда не зовёт Google напрямую.
- Слои sync разделены: `grading.py` (чистая домен-логика) / `sync_store.py`
  (запись кэша) / `sync_service.py` (оркестрация) — при переносе на
  Postgres и user-scoping меняется только store/orchestration.
- Все Classroom scope read-only (ADR-0002/0017); OIDC identity scopes нужны
  только для профиля; teacher mode — per-course роль (ADR-0017).
- Схема кэша с апсёртами по PK; зеркальная очистка stale-курсов.
- Тесты (`tests/`) hermetic: отдельный `GC_DASHBOARD_DATA_DIR`, create/drop
  схемы на каждый тест.

---

## 2. Целевая архитектура (зафиксирована)

```text
Internet
   ↓
Caddy (HTTPS, автоматический TLS) — единственная точка входа
   ↓  same public origin (например https://monkstonecor.pp.ua/)
   ├── статика React (frontend/dist) — раздаёт Caddy
   └── /api/* → FastAPI (Uvicorn)
                 ├── users / sessions / oauth_tokens (PostgreSQL)
                 ├── web OAuth flow (отдельный Web-application клиент Google)
                 ├── per-user sync (планировщик/воркеры, этап 5)
                 └── PostgreSQL — основной прод-стор (SQLite не используется)
```

Платформа: Linux VPS, Docker + Compose, Caddy (auto-TLS), PostgreSQL,
FastAPI + Uvicorn. `/api` принадлежит FastAPI; статика — reverse-proxy.
Пользователь не ставит ни Python, ни Node, ни exe: всё работает из браузера.

Ключевые запреты (из промпта миграции, §2/§8):

- SQLite — не основной прод-база.
- Desktop loopback OAuth — не основной флоу хостед-версии; для неё заводится
  отдельный клиент Google типа **Web application** с redirect URI вида
  `https://<домен>/api/auth/callback` (HTTPS, точное совпадение с GCP).
- Секреты сервера — только через env/secret-механизм хостинга; никогда в
  Git, фронтенд-ассеты, логи, образы.
- OAuth refresh/access токены пользователей — в БД (зашифрованные на
  уровне приложения), никогда в JSON-ответах или cookies браузера.

---

## 3. Инвентарь one-user-допущений (по файлам)

### backend/auth.py

| # | Место | Допущение | Куда мигрировать |
| --- | --- | --- | --- |
| A1 | `TOKEN_FILE` (config.py), `load_credentials`, `_save_credentials`, `logout`, `get_valid_credentials` | один файл токена на процесс | `oauth_tokens` (БД, на пользователя) |
| A2 | `_login_state`, `_login_lock`, `_run_login_flow`, `start_login`, `login_status` | глобальное состояние «идёт логин» на процесс | hosted: per-attempt OAuth `state`, привязанный к браузерной сессии; desktop остаётся как есть |
| A3 | `_refresh_lock` | сериализация рефрешей без ключа пользователя | per-user refresh coordination |
| A4 | `_CallbackServer`, loopback redirect `http://127.0.0.1:<port>/` | локальный consent; redirect URI динамический | hosted: фиксированный HTTPS redirect URI Web-клиента |
| A5 | `require_credentials()` | креденшелы «текущего» единственного пользователя | `get_current_user` → per-user creds (этапы 2 и 4) |
| A6 | после логина `request_soon()` — один глобальный sync | sync всего процесса | per-user job (этап 5) |

### backend/config.py

| # | Место | Допущение |
| --- | --- | --- |
| C1 | `TOKEN_FILE`, `DATABASE_FILE` (SQLite в DATA_DIR) | один токен/одна база на машину |
| C2 | `CREDENTIALS_FILE` / `embedded_secrets` | Desktop-клиент; для хостеда нужен отдельный Web-клиент, secret через env |
| C3 | `FRONTEND_ORIGINS = [localhost:5173]` | локальные CORS; прод-домен должен приходить из env |
| C4 | `SYNC_MAX_WORKERS = 16`, `SYNC_INTERVAL_MINUTES` | размер пула и расписание рассчитаны на 1 пользователя; при N пользователей общий бюджет квот и воркеров нужно пересчитывать (этапы 5, 9) |

### backend/api.py

| # | Место | Допущение |
| --- | --- | --- |
| P1 | `_profile_cache` / `_profile_lock` / `PROFILE_TTL_SECONDS` | один профиль на процесс, кэш без ключа пользователя |
| P2 | `_build_auth_status`, `/api/auth/*` | статус всегда одного аккаунта |
| P3 | Все data-ручки (`/courses`, `/assignments`, `/grades`, `/calendar`, `/status`, `/courses/{id}…`, `/courses/{id}/students…`) | читают ВСЕ строки кэша без фильтра по пользователю → в хостед-версии это IDOR по умолчанию: без `get_current_user` данные видны любому |
| P4 | `DELETE /api/cache` → `reset_cache` | « destructive: стирает весь кэш процесса» — в мультиюзере должно стирать только кэш вызывающего |
| P5 | `_role_map`, `_course_role` | роль читается из единственной строки `CourseRole` без user-измерения |
| P6 | `student_grades`: проверка `student_id != "me"` только против роли курса | в мультиюзере право читать чужие оценки должно проверяться от `get_current_user` (этап 4) |

### backend/models.py (схема данных)

| # | Проблема |
| --- | --- |
| M1 | Ни в одной таблице нет `user_id`: `Course`, `CourseWork`, `StudentSubmission`, `CourseRole`, `CourseStudent`, `CourseWorkSubmission`, `SyncState` — глобальные |
| M2 | `Course.id` = Google `course_id` как PK → два пользователя в одном курсе будут конфликтовать (PK-коллизия) и делить одни строки |
| M3 | `StudentSubmission` PK `(course_id, coursework_id)` — «свои» сабмишены ровно одного аккаунта |
| M4 | `SyncState` — глобальные ключи `last_sync`/`last_sync_error` на процесс |
| M5 | `CourseStudent.user_id` — это Google user id (нормально), но roster не привязан к владельцу курса |

### backend/main.py

| # | Место | Допущение |
| --- | --- | --- |
| S1 | `TRUSTED_HOSTS = ("127.0.0.1", "localhost")` + middleware `enforce_local_only` | жёстко локальный Host: хостед-домен за прокси будет отбиваться 403; нужно env-управляемое (этап 7) |
| S2 | CORS `allow_origins=FRONTEND_ORIGINS` | только localhost |
| S3 | `lifespan` → `start_background_sync()` | один глобальный цикл на старте процесса |
| S4 | Bind на `127.0.0.1` (launcher) | локальная защита вместо настоящей аутентификации |

### backend/sync_service.py / sync_store.py / background_sync.py

| # | Место | Допущение |
| --- | --- | --- |
| Y1 | `_SYNC_LOCK`, `sync_now()` | один sync на процесс |
| Y2 | `_do_sync()` → `auth.get_valid_credentials()` | креденшелы не параметризованы пользователем |
| Y3 | `_purge_stale_courses(db, active_ids)` | «не вернулось — значит чужое»: в мультиюзере удалит данные других пользователей; purge обязан быть по `user_id` |
| Y4 | `reset_cache` | удаляет ВСЕ таблицы целиком |
| Y5 | `get_submission(db, …, "me", is_teacher=…)` | сентинел-пользователь `"me"` вместо id реального пользователя |
| Y6 | `background_sync`: `_stop`/`_scheduler`/`_runs`, старт при `lifespan` | глобальное расписание; требуется per-user scheduler/worker (этап 5) |

### backend/path_config.py, launcher.py

| # | Место | Допущение |
| --- | --- | --- |
| L1 | `DATA_DIR = %LOCALAPPDATA%\GoogleClassHelp` (frozen) | данные на машину, не на пользователя сервиса; для хостеда данные — в PostgreSQL |
| L2 | single-instance mutex, tray, `webbrowser.open`, state-файл порта | чисто desktop; в хостед-пути не участвует |

### frontend/src

| # | Место | Допущение |
| --- | --- | --- |
| F1 | `api.ts`: `login()`/`logout()` — POST, ждут `AuthStatus` | в хостед-флоу логин станет redirect на `/api/auth/login` → Google → callback; фронтенд должен уметь переход и 401-обработку (этап 7) |
| F2 | `DataContext.tsx`, `Settings.tsx`, `Dashboard.tsx`, `Subjects.tsx` | гейтинг только по `status.authenticated`; нет cookie-сессий, нет «вы зашли под другим аккаунтом» |
| F3 | Ошибки сети трактуются как «локальный бэкенд недоступен» (fallback на кэш) | формулировки и поведение на 401 нужно уточнить (этап 7) |

### tests/

| # | Примечание |
| --- | --- |
| T1 | `test_foreign_host_is_forbidden`, `test_same_origin_post_is_allowed` — зашитые localhost-допущения; при переходе Host/Origin на env тесты обновляются (этап 7) |
| T2 | `test_api_auth` проверяет поведение с одним токеном; потребуются тесты мульти-пользователя (этап 10) |

### Документы

- README.md: «локальный дашборд», `%LOCALAPPDATA%`, exe-поставка — дополнится
  разделом хостед-развёртывания на этапе 10.
- ADR: 0001 (локальная слоёная архитектура), 0003 (SQLite-кэш), 0016
  (Nuitka), 0018 (single-instance), 0019 (loopback OAuth) — остаются
  валидными для desktop-билда; для хостеда понадобятся новые ADR
  (web OAuth + sessions, Postgres, user isolation). 0006
  (settings в localStorage) остаётся per-browser, не противоречит мультиюзеру.

---

## 4. Классификация глобального состояния (§47)

Категории: **1** — неизменяемая конфигурация; **2** — безопасная
процесс-глобальная инфраструктура; **3** — кэш, которому нужны ключи
пользователя; **4** — пользовательское состояние → БД/session-слой.

| Глобал | Место | Категория | Решение |
| --- | --- | --- | --- |
| `SCOPES` | auth.py | 1 | остаётся |
| `SYNC_MAX_WORKERS`, `SYNC_INTERVAL_MINUTES` | config.py | 1 (значения пересчитать для мультиюзера: этапы 5, 9) | env, ревизия на этапах 5/9 |
| `FRONTEND_ORIGINS`, `TRUSTED_HOSTS` | config.py / main.py | 1, но значения desktop-специфичны | сделать env-управляемыми (этап 7) |
| `DATA_DIR`, `LOGS_DIR`, `DATABASE_FILE`, `TOKEN_FILE` | path_config.py / config.py | 1 (пути) + 4 (содержимое токена) | пути остаются для desktop; токен → `oauth_tokens` |
| `CREDENTIALS_FILE`, `embedded_secrets` | config.py / build_secrets.py | 1 для desktop | хостед: Web-клиент через env; base64-встраивание — НЕ для серверных секретов |
| `engine`, `SessionLocal`, `get_db`, SQLite-прагмы | database.py | 2 (инфраструктура) | движок меняется на Postgres (этап 3), сам паттерн остаётся |
| `_login_state`, `_login_lock` | auth.py | 4 | desktop: остаётся; hosted: per-attempt OAuth state (этап 2) |
| `_refresh_lock` | auth.py | 3 | per-user рефреш-координация (этап 2+) |
| `_profile_cache`, `_profile_lock` | api.py | 3 | ключ по user_id или профиль в `users` при логине (этап 2/4) |
| `_SYNC_LOCK` | sync_service.py | 3 | per-user sync-локи (этап 5) |
| `_stop`, `_start_lock`, `_scheduler`, `_runs` | background_sync.py | 2 (инфраструктура планировщика) + jobs per-user | переработка на scheduler/worker (этап 5) |
| `sync_state` (rows `last_sync`, `last_sync_error`) | models/sync_store | 4 | per-user строки (этап 3/4) |
| launcher mutex/tray/state-file | launcher.py | 2, desktop-only | не участвует в хостед-пути |
| `_CallbackServer` и весь loopback-флоу | auth.py | 2, desktop-only (ADR-0019) | остаётся для desktop; hosted — отдельный web-флоу |

Слепо удалять глобалы нельзя: desktop-путь обязан продолжать работать
(coexistence — этап 8). Изменения в hosted-режиме вводятся отдельными
модулями/ветками по режиму запуска.

---

## 5. Что должно стать user-scoped (сводка)

- **Данные:** все 7 таблиц кэша — с измерением владельца; PK `Course`
  больше не может быть голым Google course_id (этап 3: схема с user-скоупом
  и корректными unique-ограничениями).
- **Креденшелы:** `oauth_tokens(user_id, …)` вместо `token.json`;
  шифрование полей на уровне приложения ключом из env (этап 2).
- **Сессии:** `users` + `sessions`, opaque session-токен в HttpOnly cookie
  (этап 2).
- **Профиль:** `users.display_name/email` при логине; кэш профиля — по
  user_id или из таблицы.
- **Sync:** состояние (`last_sync`, ошибки), локи, расписание и purge — по
  пользователю (этапы 4–5).
- **API:** каждая ручка `/api/*` получает зависимость текущего пользователя
  (этап 4), `DELETE /api/cache` стирает только данные вызывающего.
- **Роли:** teacher/student остаётся per-course (ADR-0017), но против
  реального `get_current_user`.

## 6. Обнаруженные риски безопасности (для последующих этапов)

1. **Данные без аутентификации.** Сегодня `localhost-bind + host-guard`
   заменяют вход: data-ручки отдают кэш любому, кто достучался. В хостеде
   сначала появляется сессия (этап 2), потом user-scoping (этап 4) — до
   этапа 4 открывать доступ наружу нельзя.
2. **IDOR-поверхность:** `/courses/{id}/students/{student_id}/grades`
   (P6), `DELETE /api/cache` (P4), purge-логика (Y3).
3. **Секреты:** web-клиент secret и ключи шифрования — только env;
   `embedded_secrets` (base64) не переносится в серверный контур.
4. **Логи:** существующий код логирует URL consent (без токенов) — ок, но
   при реализации web-флоу запрещено логировать код/token/refresh (этап 2).
5. **Cookies/CSRF:** отсутствуют; при введении сессий задать
   `HttpOnly; Secure; SameSite=Lax` и CSRF-стратегию (этап 8).

## 7. Порядок изменений

Порядок фиксирован промптом миграции (§81): сначала модель приложения
(этапы 1–4: аудит → web OAuth/sessions → Postgres → user isolation),
потом синхронизация (этап 5), API (6), фронтенд/конфиг (7),
desktop-коexistence (8), лимиты (9), тесты/деплой (10). Docker не
начинается, пока модель приложения не станет корректной.

Результаты этапа 2 (web OAuth, sessions, oauth_tokens, secret-management)
строятся на выводах этого аудита: A2/A3/A5/A6/C1/C2/P1/P2 + категории 3–4
из §4.
