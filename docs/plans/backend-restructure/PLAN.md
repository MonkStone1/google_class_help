# План реструктуризации бекенда (ADR-0039)

Статус: Этапы 0–1 выполнены, Этапы 2–4 запланированы
Дата: 2026-02-10
Источник проблемы: `backend/api.py` — 1692 строки, 23 эндпоинта и ~20 приватных
хелперов в одном файле; 39 плоских модулей в одной папке; ни одного
автоматического ограничения, которое помешало бы этому повториться.

Полный план: [`docs/plans/backend-restructure/PLAN.md`](PLAN.md) ·
Правила слоёв: [`docs/BACKEND_STRUCTURE.md`](../../BACKEND_STRUCTURE.md) ·
Решение: [`ADR-0039`](../../adr/adr-0039-layered-backend-packages.md)

---

## 1. Диагностика (факты, снятые из кода)

Реальные размеры модулей (`(Get-Content).Count`):

| Строк | Файл | Смешанные ответственности |
|---|---|---|
| **1692** | `api.py` | HTTP-хендлеры + SQL-агрегаты + кэш профиля + сборка Pydantic |
| 721 | `sync_store.py` | запись кэша |
| 666 | `hosted_auth.py` | роутеры OAuth + сессии + шифрование |
| 651 | `sync_service.py` | оркестрация синка |
| 564 | `launcher.py` | desktop entry (Nuitka) |
| 548 | `config.py` | все env-константы вперемешку |
| 517 | `main.py` | `create_app` = 310 строк с 4 вложенными middleware-замыканиями |
| 451 | `sync_scheduler.py` | планировщик |
| 423 | `feedback_admin_api.py` | роутер |
| 406 | `classroom_api.py` | транспорт Google |

Всего 11 776 строк в 39 модулях. `backend/` добавлен в `sys.path`, поэтому все
импорты верхнего уровня (`from config import ...`, `from models import ...`).

Прецедент разбиения уже есть в проекте: `sync.py` → `grading.py` +
`sync_store.py` + `sync_service.py` + фасад `sync.py` (`docs/CODE_REVIEW_BACKEND.md`
§2.2). Приём рабочий, просто не был применён дальше.

---

## 2. Жёсткие ограничения (почему нельзя просто разложить файлы по папкам)

1. **Плоские импорты завязаны в 8 местах:** `pytest.ini:3`,
   `tests/conftest.py:18`, `migrations/env.py:24`, `tools/dump_openapi.py:25`,
   `tools/classroom_smoke.py:22`, `tools/check_oauth_flow.py:37`,
   `tools/generate_hosted_secrets.py:24`, подпроцесс в
   `tests/test_stage8_coexistence.py`.
2. **Nuitka/onefile desktop (ADR-0016).** `path_config.py:48` считает
   `BACKEND_DIR = Path(__file__).resolve().parent`, и в frozen-сборке это корень
   `dist`. Отсюда `RESOURCE_DIR` → `frontend/dist`; `build.bat` компилирует
   `backend\launcher.py`; `launcher.py:40` делает `from main import app`;
   `--include-module=embedded_secrets`. Сворачивание `backend/` в один пакет
   ломает desktop-сборку.
3. **Тесты патчат приватные символы:** `api._cached_profile`,
   `api._reset_profile_cache`, `api._profile_cache`, `api._build_auth_status`,
   `api.ClassroomClient`, `api.build_service` (`tests/test_user_isolation.py`,
   `tests/test_stage9_limits_capacity.py`, `tests/test_teacher_mode.py:300`),
   а также `main.ALLOWED_HOSTS`, `main.RATE_LIMIT_*`, `config.SUPER_ADMIN_EMAIL`,
   `attachments.FEEDBACK_*`, `sync_service.SYNC_MAX_CONCURRENT_USERS`,
   `sync_scheduler.run_user`, `sync_worker.select_due_users`. Реэкспорт-шимы здесь
   **не спасают**: `monkeypatch.setattr(api, "X")` патчит атрибут пакета, а не
   подмодуля, и вызывающий код продолжит звать оригинал.
4. **Цикл импортов:** `api.py` → `ownership` → `hosted_auth` → `api`.
   `hosted_auth.py:630` делает `from api import _user_out` **лениво** — специально.
5. **OpenAPI-контракт закоммичен** (`frontend/openapi.json` →
   `npm run gen:api:file` → `src/api-schema.d.ts`). `operationId` выводится из
   **имени функции** + пути, поэтому переименование хендлера, добавление `tags=`
   или перестановка `include_router` меняют схему и ломают фронтенд. В `main.py`
   роутер `hosted_auth` включается **раньше** `api`, чтобы его `/api/auth/*`
   затеняли desktop-версии.
6. **CI минимальный** (`.github/workflows/ci.yml:44-46`): `ruff check backend` +
   `pytest`. Pyright не запускается.

**Вывод:** `backend/` обязан остаться корнем `sys.path`. Новая структура
---

## 3. Целевая структура

```text
backend/                      # остаётся корнем sys.path
├── main.py                   # точка входа: create_app + app (цель ≤60 строк)
├── launcher.py               # desktop/Nuitka entry — НЕ ТРОГАЕМ (ADR-0016)
├── path_config.py            # НЕ ТРОГАЕМ — привязан к Nuitka-путям
├── build_secrets.py          # утилита сборки — оставить
├── maintenance.py            # удаление данных пользователя — оставить плоским
│
├── edge/                     # «production edge» (ADR-0026): то, что стоит ПЕРЕД приложением
│   ├── lifespan.py           # старт/стоп планировщиков
│   ├── middleware.py         # фабрики: CORS, session gate, throttle, security headers
│   ├── origin_guard.py       # Host/Origin-проверки
│   ├── security.py           # Content-Security-Policy
│   └── static.py             # SPAStaticFiles + fallback
│
├── core/                     # инфраструктура: ноль домена, ноль FastAPI
│   ├── config.py  paths.py  metrics.py  rate_limit.py
│   ├── logging_filters.py    # ← access_log.py
│   └── capacity.py  crypto.py
│
├── db/                       # хранилище
│   ├── session.py            # ← database.py (engine/Base/get_db)
│   └── models/               # classroom.py ← models.py, accounts.py ← models_auth.py,
│                             # feedback.py ← models_feedback.py, admins.py ← models_admin.py
│
├── google/                   # единственное место контакта с Google
│   ├── classroom.py          # ← classroom_api.py
│   ├── credentials.py        # ← google_credentials.py
│   └── oauth_transport.py
│
├── sync/                     # пайплайн синхронизации
│   ├── __init__.py           # ФАСАД (бывший sync.py) — совместимость api.py/background_sync
│   ├── store.py service.py scheduler.py worker.py background.py
│
├── auth/                     # аутентификация и роли
│   ├── identity.py  ownership.py  roles.py  desktop.py  hosted.py
│
├── feedback/                 # service.py, attachments.py
│
├── schemas/                  # dashboard.py, feedback.py, admins.py
│
└── api/                      # ТОЛЬКО HTTP: тонкие хендлеры, ноль SQL, ноль Google
    ├── __init__.py           # router-сборка: include_router(...)
    ├── deps.py               # current_user_id
    ├── identity.py           # кэш профиля + проекция UserOut/AuthStatus
    ├── guards.py             # 404/403-переводчики
    ├── queries/              # чтение кэша, НИКАКОГО fastapi
    └── routes/               # по одному файлу на ресурс
```

Направление зависимостей — единственная разрешённая стрелка:

```text
core/  ←  db/  ←  google/  ←  sync/  ←  api/routes  ←  main.py
                     ↖  auth/  ↖  feedback/
```

* `core/` и `grading.py` не знают про FastAPI, SQLAlchemy-сессии и Google.
* `api/queries/**` не импортируют `fastapi` (только SQLAlchemy + схемы).
* `api/routes/**` не импортируют `google*`, `sync_store`, `sync_service`.
* Никаких `utils.py` / `helpers.py` / `common.py` — это новая свалка.

Подробности и бюджеты строк — в [`docs/BACKEND_STRUCTURE.md`](../../BACKEND_STRUCTURE.md).

---

## 5. Этап 1 — разбить `api.py` ✅ выполнен

`api.py` (1692 строки) → 18 файлов пакета `backend/api/`. Карта переноса по
диапазонам строк исходника:

| Строки `api.py` | Куда | Что внутри |
|---|---|---|
| 108–241 | `api/identity.py` | `_profile_cache`, `_cached_profile`, `_reset_profile_cache`, `_user_out`, `_build_auth_status`, `_is_authenticated` |
| 244–297 | `api/routes/auth.py` | `/auth/status`, `/me`, `/auth/login`, `/auth/logout` |
| 303–311 | `api/deps.py` | `current_user_id` |
| 317–393, 420–534 | `api/queries/assignments.py` | `_role_map`, `_build_assignment_out`, `_load_assignments`, `_assignment_by_id`, `_student_only` |
| 394–418, 537–722 | `api/queries/courses.py` | `_all_courses`, `_active_courses`, `_course_stats_sql` |
| 894–1000 | `api/queries/dashboard.py` | `_student_totals_sql` |
| 1308–1407, 1587–1609 | `api/queries/teacher.py` | `_roster_rows`, `_student_out`, `_submission_out_for`, `_submissions_for_work`, `_grade_submissions` |
| 728–739, 1410–1538 | `api/routes/courses.py` | `/courses`, `/courses/{id}`, `/coursework`, `/students`, `/grades` |
| 742–794, 1541–1584 | `api/routes/assignments.py` | `/assignments`, `/upcoming`, `/overdue`, `/coursework/{id}`, `/submissions` |
| 797–866, 1612–1692 | `api/routes/grades.py` | `/grades`, `/students/{id}/grades` |
| 869–891 | `api/routes/calendar.py` | `/calendar` |
| 1003–1037 | `api/routes/status.py` | `/status` |
| 1040–1167 | `api/routes/sync.py` | `/sync`, `_is_sync_running`, `_restart_desktop_sync` |
| 1170–1206 | `api/routes/cache.py` | `/cache`, `/me/cache` |
| 1209–1279 | `api/routes/account.py` | `DELETE /me/google`, `DELETE /me` |
| 1285–1305 | `api/guards.py` | `_get_course`, `_course_role`, `_require_teacher` |
| 105 | `api/__init__.py` | `router = APIRouter(prefix="/api")` + `include_router` |

Приватные имена сохранены с подчёркиванием: переименование ломает
`monkeypatch`-цели в тестах без выигрыша. Снятие подчёркивания — отдельная
задача после Этапа 1.

### Правило, без которого тихо ломаются 4 теста

Внутри пакета обращаться к соседнему модулю **через модуль**, а не через прямой
`from ... import имя`:

```python
from api import identity                      # ✅ identity._cached_profile(...)
# from api.identity import _cached_profile    # ❌ связывается при импорте
```

Это ровно тот приём, который уже применён в проекте (`import ownership` +
`ownership.get_current_user`). Нарушение здесь — единственный способ тихо
сломать `test_user_isolation.py`, `test_stage9_limits_capacity.py` и
`test_teacher_mode.py`.

### Что изменилось в существующих файлах

| Файл | Правка |
|---|---|
| `backend/api.py` | удалён, заменён пакетом `backend/api/` (в одном коммите — иначе двойной импорт) |
| `backend/hosted_auth.py` | `from api import _user_out` → ленивый `from api.identity import _user_out` |
| `tests/test_user_isolation.py` | `import api` → `from api import identity`, все `api._*` → `identity.*` |
| `tests/test_stage9_limits_capacity.py` | то же |
| `tests/test_teacher_mode.py` | `"api._cached_profile"` → `"api.identity._cached_profile"` |

`backend/main.py` **не менялся**: `from api import router` (строка 49) одинаково
---

## 6. Этап 2 — `main.py` (517 → ~60) и `edge/` (запланирован)

Вынести `lifespan`, 4 middleware-замыкания, origin-guard, CSP,
`SPAStaticFiles`. Побочный эффект: middleware становятся тестируемыми по
отдельности — сейчас их нельзя вызвать иначе как через `create_app`.

Побочная правка тестов: `tests/test_stage7_frontend_config.py` и
`tests/test_stage9_limits_capacity.py` патчат `main.ALLOWED_HOSTS` /
`main.RATE_LIMIT_*`; после выноса чтение идёт из `edge/*`, значит патчи
переводятся на новый модуль (около 8 строк в 2 файлах).

---

## 7. Этап 3 — доменные пакеты (запланирован)

`sync/` → `google/` → `auth/` → `feedback/` → `db/` → `schemas/` → `core/`.

Правило: **переезд 1 файл → 1 модуль, без склейки и разделения**, иначе рвутся
`monkeypatch`-цели. `auth.py` → `auth/desktop.py` переезжает атомарно, и только
тогда `api/identity.py` → `auth/identity.py` (в Этапе 1 этот конфликт имён не
позволяет создать пакет `auth/` — там лежит `auth.py`).

Обновляются в том же коммите: `tests/`, `migrations/env.py:26-31`,
`compose.yml:125`, `compose.local.yml:119`, `database.py::_import_models`,
`tools/{dump_openapi,classroom_smoke,check_oauth_flow,generate_hosted_secrets}.py`.

Остаточные толстяки дробить там же: `sync/store.py` (721) →
`store/{courses,coursework,submissions,status}.py`; `auth/hosted.py` (666) →
`hosted/{routes,session,oauth_flow}.py`.

---

## 8. Этап 4 — ограждения (запланирован)

`tests/test_backend_structure.py`:
1. ни один модуль в `backend/**` не длиннее 400 строк (с явным списком исключений);
2. `core/**` и `grading.py` не импортируют `fastapi` / `googleapiclient`;
3. `api/queries/**` не импортируют `fastapi`;
4. `api/routes/**` не импортируют `google*`, `sync_store`, `sync_service`;
5. в корне `backend/` нет файлов-долгов (только фасады ≤ 60 строк).

Плюс `banned-api` в `ruff.toml`, джоб `npx pyright` в CI, раздел в `README.md`.

---

## 9. Что не трогаем ни в одном этапе

`path_config.py` и `launcher.py` (Nuitka, ADR-0016), `credentials.json`,
`build.bat`, `pytest.ini`, `Dockerfile CMD`, HTTP-контракт. `backend/` остаётся
корнем `sys.path` — поэтому 8 мест с `sys.path.insert`/`pythonpath` и оба
compose-файла не требуют изменений.

---

## 10. Риски и откат

| Риск | Что делаем |
|---|---|
| Тихая смена API при переносе | `tests/test_api_contract.py` + сравнение `dump_openapi.py` с закоммиченным `frontend/openapi.json` |
| Циклы импортов при разделении | `api/identity.py` импортируется из `hosted_auth.py` лениво, как сейчас |
| Двойной импорт модуля (module vs package) | переезд атомарный в одном коммите, шимы-реэкспорты не оставляем |
| Сломалась desktop-сборка | `path_config.py` / `launcher.py` не трогаем |
| Тесты «починили» ослаблением | `pytest` обязан быть зелёным с тем же числом тестов |

**Откат:** каждый этап — отдельный коммит, `git revert` этапа.
работает и для модуля, и для пакета.

### Инварианты (нарушение = откат)

1. Ни одного изменения в путях, методах, именах хендлеров, `response_model`,
   `Query(...)`-описаниях → `operationId` в OpenAPI не поедет.
2. Никаких новых `tags=` — иначе изменится `frontend/openapi.json`.
3. Порядок `include_router` даёт тот же приоритет маршрутов; роутер
   `hosted_auth` по-прежнему включается раньше.
4. Каждый docstring переезжает **вместе с кодом**, включая ссылки на §/ADR.
---

## 4. Этап 0 — страховка и документация ✅ выполнен

* `docs/plans/backend-restructure/PLAN.md` — этот файл.
* `docs/BACKEND_STRUCTURE.md` — карта слоёв, правила, рецепт нового домена.
* `docs/adr/adr-0039-layered-backend-packages.md` — решение.
* `tests/test_api_contract.py` — snapshot-контракт: 41 desktop-операция +
  4 hosted-only, плюс проверка, что каждый хендлер `/api` живёт в `api/routes/`.

Snapshot снимался по `app.openapi()`, а не по `app.routes`: установленная версия
FastAPI оборачивает `include_router` в `_IncludedRouter`, поэтому в
`app.routes` лежат обёртки, а не плоские `APIRoute`. OpenAPI — и есть контракт,
из которого frontend генерирует типы, так что это даже точнее.
строится **пакетами внутри `backend/`** — тогда `uvicorn main:app`,
`Dockerfile CMD`, `build.bat`, `pytest.ini`, `launcher.py:40` и README остаются
нетронутыми.