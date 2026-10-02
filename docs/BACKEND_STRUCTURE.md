# Структура бекенда

Карта слоёв, разрешённые направления импортов и бюджеты строк. Решение —
[ADR-0039](adr/adr-0039-layered-backend-packages.md), план работ —
[`docs/plans/backend-restructure/PLAN.md`](plans/backend-restructure/PLAN.md).

## Почему `backend/` остаётся корнем `sys.path`

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
core/  ←  db/  ←  google/  ←  sync/  ←  api/routes  ←  main.py
                     ↖  auth/  ↖  feedback/
```

| Слой | Что в нём | Чего быть не должно |
|---|---|---|
| `core/` | config, пути, логирование, метрики, rate limit, crypto | FastAPI, SQLAlchemy-сессий, домена |
| `db/` | engine/сессии, модели | бизнес-логики, HTTP |
| `google/` | `classroom.py`, `credentials.py`, `oauth_transport.py` | FastAPI-роутов |
| `sync/` | `store.py` (запись кэша), `service.py` (оркестрация), `scheduler.py`, `worker.py`, `background.py` | HTTP-роутов |
| `auth/` | `identity.py`, `ownership.py`, `roles.py`, `desktop.py`, `hosted.py` | SQL-запросов к кэшу |
| `feedback/` | `service.py`, `attachments.py` | HTTP |
| `schemas/` | Pydantic-модели ответа | SQL, Google |
| `api/routes/` | тонкие хендлеры, `Depends`, `HTTPException` | SQL-агрегатов, `google*`, `sync_store` |
| `api/queries/` | чтение кэша (SQLAlchemy) | `fastapi`, `HTTPException` |
| `api/guards.py` | перевод доменных «нет такого курса / не учитель» в 404/403 | — |
| `main.py` | сборка приложения: роутеры, middleware, lifespan | логики домена |

`grading.py` — чистый домен: ноль импортов Google, FastAPI и SQLAlchemy.

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

1. `api/identity.py` импортирует `classroom_api` — кэш профиля desktop-сборки
   ходит в Google userinfo. Убрать можно только вместе с переездом
   `classroom_api.py` в `google/` (Этап 3); сегодня это всякий раз один
   сетевой вызов за пять минут на пользователя.
2. `api/routes/sync.py` делает локальный `from sync_store import sync_status`
   внутри функции — наследие того же `api.py`. Исчезнет, когда `sync/` станет
   пакетом и появится `sync.status()`; до тех пор правило для этого файла —
   «не импортировать `sync_service`/`sync_store` на верхнем уровне».

`tests/test_backend_structure.py` (Этап 4) должен проверять эти правила с этими
двумя исключениями, иначе тест будет красным на честном коде и его придётся
ослабить целиком.

## Слои в процессе миграрации

Этапы 3–4 ещё не выполнены, поэтому часть доменных модулей пока лежит в корне
`backend/` плоско (`sync_store.py`, `hosted_auth.py`, `config.py` и т.д.).
Карта в `docs/plans/backend-restructure/PLAN.md` §3 — целевая.
Выполнено: `api/` (Этап 1) и `edge/` (Этап 2).

## Бюджеты строк

| Что | Файл | Лимит |
|---|---|---|
| Роут | `api/routes/<ресурс>.py` | ≤ 250 |
| Запрос к кэшу | `api/queries/<ресурс>.py` | ≤ 350 |
| Доменный модуль | `sync/store.py`, `auth/hosted.py` и т.п. | ≤ 400 |
| Инфраструктура | `core/*` | ≤ 400 |
| Production edge | `edge/*` | ≤ 400 |
| Сборка приложения | `main.py` | ≤ 200 |
| Фасад совместимости | `sync.py`, `sync/__init__.py` | ≤ 60 |

Автоматическая проверка — `tests/test_backend_structure.py` (Этап 4).

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
про `google*`. Это проверяется в Этапе 4.

## Контракт, который нельзя ломать переездом

* Пути, методы и **имена функций-обработчиков** (`operationId` в OpenAPI
  выводится из имени функции + пути). Проверяется
  `tests/test_api_contract.py`.
* `response_model`, описания `Query(...)`, статус-коды 401/403/404/409/429/503.
* Никаких новых `tags=` без изменения `frontend/openapi.json` и
  `npm run gen:api:file`.
* Порядок подключения роутеров: `hosted_auth` включается раньше `api`, иначе
  desktop-версии `/api/auth/*` затенят hosted-версии.