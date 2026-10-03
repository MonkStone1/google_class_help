# Структура бекенда

Карта слоёв, разрешённые направления импортов и бюджеты строк. Решение —
[ADR-0039](adr/adr-0039-layered-backend-packages.md), план работ —
[`docs/plans/backend-restructure/PLAN.md`](plans/backend-restructure/PLAN.md).

## Почему `backend/` остаётся корнем `sys.path`

Фронтенд решён отдельно: `frontend/src/` делится на шесть слоёв —
`shared/`, `entities/`, `features/`, `widgets/`, `pages/`, `app/`
([ADR-0040](adr/adr-0040-layered-frontend-slices.md),
[`docs/FRONTEND_STRUCTURE.md`](FRONTEND_STRUCTURE.md)). Там слоями являются
каталоги верхнего уровня `src/`, а не пакеты: у Node-резолвинга нет проблемы
`sys.path`, которая потребовала пакетов здесь.

`backend/` добавлен в `sys.path` (`pytest.ini`, `tests/conftest.py:18`,
`migrations/env.py:24`, четыре файла в `tools/`), поэтому все модули
импортируются верхнего уровня: `from config import ...`, `from models import ...`.
Это завязано ещё и на desktop-сборку: `path_config.py:48` в frozen-режиме
(Nuitka, ADR-0016) считает `BACKEND_DIR = Path(__file__).resolve().parent`
корнем `dist`, откуда берётся путь к `frontend/dist`.

Следствие: **слоями являются пакеты внутри `backend/`**, а не один большой
пакет `backend/app/`. Благодаря этому `uvicorn main:app`, `Dockerfile CMD`,
`build.bat`, `pytest.ini` и `launcher.py` не меняются.

## Слои

```text
core/  ←  db/  ←  gapi/  ←  sync/  ←  api/routes  ←  main.py
                     ↖  auth/  ↖  feedback/
```

| Слой | Что в нём | Чего быть не должно |
|---|---|---|
| `core/` | config, пути, логирование, метрики, rate limit, crypto, `origins.py`, `http_config.py` | FastAPI, SQLAlchemy-сессий, домена |
| `db/` | engine/сессии, модели | бизнес-логики, HTTP |
| `gapi/` | `classroom.py`, `credentials.py`, `oauth_transport.py`, `timeparse.py` | FastAPI-роутов |
| `sync/` | `store/` (запись кэша), `service/` (оркестрация), `scheduler/`, `worker.py`, `background.py` | HTTP-роутов |
| `auth/` | `identity.py`, `ownership.py`, `roles.py`, `desktop.py`, `hosted/` | SQL-запросов к кэшу |
| `feedback/` | `service.py`, `attachments.py` | HTTP |
| `schemas/` | Pydantic-модели ответа | SQL, Google |
| `api/routes/` | тонкие хендлеры, `Depends`, `HTTPException` | SQL-агрегатов, `gapi.*`, `sync.store` |
| `api/queries/` | чтение кэша (SQLAlchemy) | `fastapi`, `HTTPException` |
| `api/guards.py` | перевод доменных «нет такого курса / не учитель» в 404/403 | — |
| `main.py` | сборка приложения: роутеры, middleware, lifespan | логики домена |

`grading.py` — чистый домен: ноль импортов Google, FastAPI и SQLAlchemy.

### Почему `gapi/`, а не `google/`

`backend/` — корень `sys.path`, поэтому имя каталога в нём видно всему процессу
вместе с `site-packages`. Каталог `google/` **затенил бы** установленные
namespace-пакеты `google-api-python-client`, `google-auth`, `google-auth-httplib2`:
`from google.oauth2.credentials import Credentials` перестал бы резолвиться, и
приложение падало бы на старте. Для PEP 420-пакетов опаснее: `google/` не
перекрывает их, а **сливается** с ними по порядку путей — и ломается в день,
когда порядок меняется.

`gapi/` (Google API) не совпадает ни с одним установленным распределением.
Тест `test_no_layer_shadows_an_installed_distribution` в
`tests/test_backend_structure.py` проверяет это настоящим импортом: `find_spec`
для namespace-пакета вернул бы `None` и молча прошёл.

### Внутренние пакеты: по чему делили

Три слоя выросли в пакеты, и деление шло **по назначению**, а не по размеру:

| Пакет | Модули | Почему вместе |
|---|---|---|
| `sync/store/` | `status.py`, `cache.py`, `writing.py` | переходы статуса, чтение двух таблиц и destructive-очистка, перевод payload → строки кэша |
| `sync/service/` | `_fetch.py`, `_fetching.py`, `results.py`, `common.py` | получение (fan-out к Google) и запись (транзакция) падают по-разному; `common.py` — коды исходов и политика ошибок, общая для обеих половин |
| `sync/scheduler/` | `due.py`, `_scan.py` | «кто due» — чистая арифметика времени; `SyncScheduler` отвечает на другой вопрос («сколько может идти сейчас») |
| `auth/hosted/` | `__init__.py`, `sessions.py`, `turnstile.py` | сессия — отдельный механизм от OAuth-раундтрипа; Turnstile опционален и держит единственный секрет |

Фасады (`sync/store/__init__.py`, `sync/service/__init__.py`,
`sync/scheduler/__init__.py`, `auth/hosted/__init__.py`) существуют, чтобы
вызывающий код продолжал импортировать прежние имена — и чтобы `monkeypatch`
фасада доходил до вызывающего кода, а не оставался на копии.

### Слой `edge/`

`edge/` — «production edge» (ADR-0026, §36/§38/§48): то, что стоит **перед**
приложением. Единственный слой, который знает и про HTTP, и про конфигурацию,
и про развёртывание, поэтому он же — единственное место, где middleware
регистрируются.

| Модуль | Что внутри | Чего быть не должно |
|---|---|---|
| `edge/lifespan.py` | `init_db`, старт/стот планировщиков | логики домена |
| `edge/middleware.py` | фабрики `install_throttle` / `install_session_gate` / `install_cors` / `install_host_guard` / `install_security_headers` | SQL, Google, бизнес-правил |
| `edge/origin_guard.py` | `_host_allowed`, `_request_host_allowed`, `_origin_allowed` | `fastapi`-приложения (только решения) |
| `edge/security.py` | CSP | состояния запроса |
| `edge/static.py` | `SPAStaticFiles`, `mount_frontend` | домена |

Три правила, которые этот слой держит:

1. **Конфигурация читается через объект модуля** (`config.RATE_LIMIT_*`),
   а не импортом по значению. Импорт по значению создаёт вторую копию
   константы, и `monkeypatch` на `config` перестаёт её видеть.
2. **Порядок регистрации — часть контракта.** Starlette выполняет последний
   зарегистрированный middleware внешним, поэтому порядок вызовов в
   `main.create_app` и есть порядок выполнения. Он описан в docstring
   `edge/middleware.py`.
3. **Ленивые импорты остаются ленивыми.** `background_sync`,
   `hosted_auth`, `sync_scheduler` грузятся внутри функций, иначе hosted-путь
   начнёт импортировать desktop-модули (§32/§74) — это проверяется тестом
   в подпроцессе.

### Два исключения, зафиксированные честно

Правила выше — для нового кода. Два места импортируют то, что правило запрещает,
и это перенесено из старого `api.py` как есть, а не спрятано:

1. `auth/identity.py` импортирует `gapi.classroom` — кэш профиля desktop-сборки
   ходит в Google userinfo. Сегодня это всякий раз один сетевой вызов за пять
   минут на пользователя; убрать можно только вместе с переездом этого чтения в
   `sync` (отдельная задача, не Этап 3).
2. `api/routes/sync.py` делает локальный `from sync.store import sync_status`
   внутри функции — наследие того же `api.py`. Исчезнет, когда у `sync.store`
   появится аксессор статуса, отдельный от `sync_status(db, user_id)`.

Оба исключения **проверяются тестом**, а не только комментарием:
`test_the_sync_status_read_stays_a_local_import` в
`tests/test_backend_structure.py` падает, если локальный импорт поднимется на
уровень модуля. Когда аксессор появится, тест напомнит удалить исключение из
этого документа в том же изменении.

`tests/test_backend_structure.py` (Этап 4) проверяет эти правила с этими
двумя исключениями — иначе тест был бы красным на честном коде, и его пришлось бы
ослабить целиком.

## Слои: миграция завершена

Все плоские модули разложены по пакетам (Этапы 3–4): `config.py` → `core/`,
`sync_store.py` → `sync/store/`, `hosted_auth.py` → `auth/hosted/`,
`classroom_api.py` → `gapi/`, `sync_service.py` → `sync/service/`,
`sync_scheduler.py` → `sync/scheduler/`. Плоско осталось только то, что привязано
сборкой: `main.py`, `launcher.py`, `path_config.py`, `maintenance.py`,
`build_secrets.py`, `embedded_secrets.py` (ADR-0016).

Карта в `docs/plans/backend-restructure/PLAN.md` §3 совпадает с фактической.

## Бюджеты строк

| Что | Файл | Лимит |
|---|---|---|
| Роут | `api/routes/<ресурс>.py` | ≤ 280 |
| Запрос к кэшу | `api/queries/<ресурс>.py` | ≤ 350 |
| Доменный модуль | `sync/store/status.py`, `auth/hosted/__init__.py` и т.п. | ≤ 400 |
| Инфраструктура | `core/*` | ≤ 400 |
| Production edge | `edge/*` | ≤ 400 |
| Сборка приложения | `main.py` | ≤ 200 |
| Фасад совместимости | `sync/__init__.py`, `sync/store/__init__.py` | ≤ 60 |

Роут получает 280, а не 200: хендлер плюс шов авторизации плюс маппинг в модель
ответа — и фидбек действительно принимает на одном URL и JSON, и multipart.
Модуль `api.py` в 300 строк, который эти роуты заменили, держал все
четырнадцать; смысл дробления в том, что каждый роут теперь находится по имени.

Автоматическая проверка — `tests/test_backend_structure.py` (18 тестов).

## Соглашения об именах

* `api/routes/<ресурс>.py` — ресурс во множественном числе: `courses.py`,
  `assignments.py`, `grades.py`. Не `misc.py`, не `helpers.py`.
* `<домен>/store.py` — только запись/чтение кэша; `<домен>/service.py` —
  оркестрация. Путаница между ними была исходной проблемой `sync.py`
  (`docs/CODE_REVIEW_BACKEND.md` §2.2).
* Никаких `utils.py`, `common.py`, `base.py` — это новая свалка под другим
  именем. Общий код живёт в `core/` с конкретным именем по назначению.
* Имя файла = имя, которое импортируют. Модуль не должен экспортировать
  «всё подряд» через `*`.

## Обращение к соседнему модулю

Внутри пакета — **через модуль**, а не прямым импортом функции:

```python
from api import identity                       # ✅ identity._build_auth_status(...)
from api.identity import _build_auth_status   # ❌ связывается при импорте
```

Тесты патчат `api.identity._cached_profile` и `identity.ClassroomClient`
(`tests/test_user_isolation.py`, `tests/test_stage9_limits_capacity.py`,
`tests/test_teacher_mode.py`). Прямой импорт функции свяжет её в момент
импорта модуля, `monkeypatch.setattr` попадёт в одноимённый атрибут
импортирующего модуля, а звать продолжит оригинал — тест упадёт или, что
хуже, пройдёт мимо проверки. В проекте этот приём уже используется:
`import ownership` + `ownership.get_current_user`.
Правило закреплено в `ruff.toml` (`lint.flake8-tidy-imports.banned-api`,
коды `SIBLING_NAME_IMPORT` и `STAR_IMPORT`) — список намеренно узкий:
только те модули, чьи функции патчит суита. Константа
(`from core.config import HOSTED_MODE`) в список не входит: тесты
патчат `core.config.X`, и локальная копия безвредна.

## Рецепт: добавить новый домен

1. `backend/<домен>/service.py` — бизнес-логика; `store.py` — если нужна
   запись в БД.
2. `backend/schemas/<домен>.py` — Pydantic-модели ответа.
3. `backend/api/routes/<домен>.py` — роуты; сложные чтения выносятся в
   `backend/api/queries/<домен>.py`.
4. Подключить роутер в `backend/api/__init__.py` (или в `main.py`, если домен
   не `/api/*`).
5. Тест в `tests/test_<домен>.py`.
6. Модель → `db/models/` + миграция Alembic + регистрация в
   `db/session.py::_import_models` и `migrations/env.py`.

Порядок важен: `api/queries` не должен знать про `fastapi`, а `api/routes` —
про `gapi.*` и писатели кэша. Это проверяется
`test_api_queries_do_not_import_fastapi` и
`test_api_routes_do_not_reach_into_google_or_the_cache_writers`.

## Контракт, который нельзя ломать переездом

* Пути, методы и **имена функций-обработчиков** (`operationId` в OpenAPI
  выводится из имени функции + пути). Проверяется
  `tests/test_api_contract.py`.
* `response_model`, описания `Query(...)`, статус-коды 401/403/404/409/429/503.
* Никаких новых `tags=` без изменения `frontend/openapi.json` и
  `npm run gen:api:file`.
* Порядок подключения роутеров: `auth.hosted` включается раньше `api`, иначе
  desktop-версии `/api/auth/*` затенят hosted-версии.