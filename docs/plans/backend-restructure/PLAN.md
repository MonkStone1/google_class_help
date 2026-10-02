# План реструктуризации бекенда (ADR-0039)

Статус: Этапы 0–4 выполнены (ADR-0039 закрыт на этом наборе)
Дата: 2026-02-10 · Уточнено: 2026-10-02
Источник проблемы: `backend/api.py` — 1692 строки, 23 эндпоинта и ~20 приватных
хелперов в одном файле; 39 плоских модулей в одной папке; ни одного
автоматического ограничения, которое помешало бы этому повториться.

Полный план: [`docs/plans/backend-restructure/PLAN.md`](PLAN.md) ·
Правила слоёв: [`docs/BACKEND_STRUCTURE.md`](../../BACKEND_STRUCTURE.md) ·
Решение: [`ADR-0039`](../../adr/adr-0039-layered-backend-packages.md)

---

## 0. Как читать этот план

| § | Что это | Состояние |
|---|---|---|
| 1–2 | Диагностика и ограничения — почему переезд вообще возможен | факт |
| 3 | Целевая структура `backend/` | факт, с поправкой этого плана на §3.1 |
| 4–6 | Этапы 0–2: `api/`, `edge/` | **выполнены** (коммиты `32079d5`, `1d67a13`) |
| 7 | Этап 3: доменные пакеты `core/`, `db/`, `gapi/`, `sync/`, `auth/`, `feedback/`, `schemas/` | **выполнен** |
| 8 | Этап 4: ограждения `test_backend_structure.py`, ruff, CI, README | **выполнен** |
| 9–10 | Что не трогаем, риски и откат | факт |

Каждая цифра в §§1–6 снята с кода (`git show`, `ast`, `(Get-Content).Count`).
Каждое утверждение о порядке импортов в §7 проверено обходом AST по
`backend/`, `tests/`, `tools/`, `migrations/`.

**Эта редакция исправляет** (сверка с кодом, а не правка стиля):

* восстановлен порядок секций — «Этап 0» висел после «Рисков и откат»;
* дописаны три оборванных предложения (§2 «Вывод», §5 про `main.py`,
  §10 «Откат») — их хвосты лежали в конце файла без хозяина;
* `main.py`: 161 → **162** строки, `create_app` — не 60, а **96** строк (§6);
* `api/`: 18 → **19** файлов (§5); `edge/`: 6 — верно (§6);
* «11 776 строк в 39 модулях» → **11 759 строк в 40 модулях** (§1);
* §7 переписан: вместо абзаца на 5 строк — порядок переездов, карта
  модулей, таблица целей `monkeypatch`, список правится в том же коммите;
* §3.1: **новое ограничение**, которого не было ни в плане, ни в ADR-0039, —
  слой `google/` перекрывает PyPI-пакет `google`. Проверено запуском (§3.1).

---

## 1. Диагностика (факты, снятые из кода)

Срез сделан на `bb9a3de` — коммите перед Этапом 1. Размеры сверены по blob'ам
через `git show`, чтобы не зависеть от переводов строк в рабочей копии.

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

Всего **11 759 строк в 40 модулях**. `backend/` добавлен в `sys.path`, поэтому
все импорты верхнего уровня (`from config import ...`, `from models import ...`).

Состояние после Этапов 1–2 (проверено на `1d67a13`): 64 модуля, 12 331 строка,
из них в корне `backend/` — 9 714. Два файла-толстяка исчезли, два пакета
набрали 2 617 строк, средний модуль упал с 294 до 193 строк.

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
3. **Тесты патчат приватные символы.** Полный список снят обходом `tests/` —
   16 модулей, 34 цели. Он целиком перенесён в §7.4, потому что это и есть
   карта работы Этапа 3. Здесь достаточно сути: реэкспорт-шимы их **не
   спасают** — `monkeypatch.setattr(api, "X")` патчит атрибут пакета, а не
   подмодуля, и вызывающий код продолжит звать оригинал.
4. **Цикл импортов:** `api.identity` → `ownership` → `hosted_auth` →
   `api.identity`. `hosted_auth.py:632` делает `from api.identity import _user_out`
   **лениво** — специально.
5. **OpenAPI-контракт закоммичен** (`frontend/openapi.json` →
   `npm run gen:api:file` → `src/api-schema.d.ts`). `operationId` выводится из
   **имени функции** + пути, поэтому переименование хендлера, добавление `tags=`
   или перестановка `include_router` меняют схему и ломают фронтенд. В `main.py`
   роутер `hosted_auth` включается **раньше** `api`, чтобы его `/api/auth/*`
   затеняли desktop-версии.
6. **CI минимальный** (`.github/workflows/ci.yml:45-46`): `ruff check backend` +
   `pytest`. Pyright не запускается.

**Вывод:** `backend/` обязан остаться корнем `sys.path`. Новая структура
строится **пакетами внутри `backend/`** — тогда `uvicorn main:app`,
`Dockerfile CMD`, `build.bat`, `pytest.ini`, `launcher.py:40` и README остаются
нетронутыми. Пакет — это просто каталог с `__init__.py`, поэтому плоские
импорты продолжают работать.

### Инварианты, которые переезд не вправе сломать

Это проверяемый список, а не пожелание: нарушение любого пункта означает
`git revert` этапа.

1. Ни одного изменения в путях, методах, именах хендлеров, `response_model`,
   описаниях `Query(...)` → `operationId` в OpenAPI не поедет.
2. Никаких новых `tags=` — иначе изменится `frontend/openapi.json`.
3. Порядок `include_router` даёт тот же приоритет маршрутов; роутер
   `hosted_auth` по-прежнему включается раньше.
4. Каждый docstring переезжает **вместе с кодом**, включая ссылки на §/ADR.
5. `operationId` собирается как `<имя функции>_<путь>_<метод>` — имя модуля в
   него **не входит**. Значит перенос хендлера из `feedback_api.py` в
   `api/routes/feedback.py` контракт не ломает, а вот переименование функции,
   смена пути, `response_model` или `tags` — ломает. (Проверено на списке из
   `test_api_contract.py`: `operationId` = `list_tickets_api_admin_feedback_tickets_get`
   не содержит имени модуля.)
6. Число тестов не уменьшается: «починили ослаблением» — не откат, а повод
   искать, что сломалось.

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
│   ├── config.py             # ← config.py
│   ├── origins.py            # ← часть config.py: нормализация origin/host
│   ├── logging_filters.py    # ← access_log.py
│   ├── metrics.py  rate_limit.py  capacity.py  crypto.py  proxy.py
│
├── db/                       # хранилище
│   ├── session.py            # ← database.py (engine/Base/get_db)
│   └── models/               # classroom.py ← models.py, accounts.py ← models_auth.py,
│                             # feedback.py ← models_feedback.py, admins.py ← models_admin.py
│
├── gapi/                     # единственное место контакта с Google (НЕ `google/`, см. §3.1)
│   ├── classroom.py          # ← classroom_api.py
│   ├── credentials.py        # ← google_credentials.py
│   └── oauth_transport.py    # ← oauth_transport.py
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
core/  ←  db/  ←  gapi/  ←  sync/  ←  api/routes  ←  main.py
                      ↖  auth/  ↖  feedback/
```

* `core/` и `grading.py` не знают про FastAPI, SQLAlchemy-сессии и Google.
* `api/queries/**` не импортируют `fastapi` (только SQLAlchemy + схемы).
* `api/routes/**` не импортируют `gapi*`, `sync_store`, `sync_service`.
* Никаких `utils.py` / `helpers.py` / `common.py` — это новая свалка.

### 3.1 Почему слой называется `gapi/`, а не `google/`

Это единственное отклонение от `ADR-0039` и оно обязательное.

`backend/` лежит в `sys.path`, поэтому любой каталог верхнего уровня в нём
конкурирует со всем, что установлено в `site-packages`. Имя `google` **уже
занято**: пакеты `google-auth`, `google-api-python-client` и
`google-auth-httplib2` ставят в `site-packages/google/` — причём как
**namespace-пакет (PEP 420)**, то есть каталог без `__init__.py`.

Проверено на текущем `.venv` два варианта:

| Вариант | Результат |
|---|---|
| `backend/google/` **с** `__init__.py` | `import google` резолвится в наш каталог; `from google.oauth2.credentials import Credentials` (нужен `auth.py`, `google_credentials.py`, `oauth_transport.py`) → **ModuleNotFoundError** |
| `backend/google/` **без** `__init__.py` | namespace-пакеты сливаются, `google.__path__` = наш + `site-packages`, импорт проходит — но это лотерея на порядок `sys.path` и на то, что наш каталог назван как чужой |

Первый вариант ломает приложение сразу, второй работает сегодня и завтра
сломается при любом изменении порядка импортов или при добавлении зависимости,
которая тоже зовётся `google`. Поэтому слой переименован в **`gapi/`**.
Проверено `importlib.util.find_spec` для всех имён новой структуры —
`gapi`, `core`, `db`, `sync`, `auth`, `feedback`, `schemas`, `api`, `edge`
свободны.

Одноимённые тесты для Этапа 4: `test_no_layer_shadows_an_installed_package` —
импортирует пакет и проверяет, что `__file__` не указывает в `backend/`.

Подробности и бюджеты строк — в [`docs/BACKEND_STRUCTURE.md`](../../BACKEND_STRUCTURE.md).

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

---

## 5. Этап 1 — разбить `api.py` ✅ выполнен

`api.py` (1692 строки) → **19** файлов пакета `backend/api/`. Карта переноса по
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

`backend/main.py` **не менялся**: `from api import router` (строка 48) одинаково
работает и для модуля, и для пакета.

---

## 6. Этап 2 — `main.py` (517 → 162) и `edge/` ✅ выполнен

`main.py` разделён на 6 модулей пакета `backend/edge/`. Карта переноса:

| Строки `main.py` | Куда | Что внутри |
|---|---|---|
| 119–159 | `edge/lifespan.py` | `lifespan` — `init_db`, `install_secret_redaction`, старт/стоп `background_sync` / `sync_scheduler` |
| 162–201 | `edge/origin_guard.py` | `_host_allowed`, `_request_host_allowed`, `_origin_allowed` |
| 79–116 | `edge/security.py` | `_build_content_security_policy`, `CONTENT_SECURITY_POLICY` |
| 236–303 | `edge/middleware.py` | `install_throttle` |
| 305–359 | `edge/middleware.py` | `install_session_gate` |
| 363–373 | `edge/middleware.py` | `install_cors` |
| 375–408 | `edge/middleware.py` | `install_host_guard` |
| 448–482 | `edge/static.py` | `SPAStaticFiles`, `mount_frontend` |
| 491–512 | `edge/middleware.py` | `install_security_headers` |
| 204–517 | `main.py` | `create_app` + `app` |

`main.py` — 162 строки, из них **96** — `create_app` (`ast`-замер: `def` с
строки 64, `return app` на 159). Остальное — docstring, импорты и два
health-эндпоинта, которые обязаны остаться в `main`: `tests/test_api_contract.py`
требует, чтобы у каждого хендлера был собственный `operationId`, а `/api/health`
и `/api/ready` регистрируются прямо на `app`, минуя роутеры.

### Побочный эффект, ради которого этап и делался

Middleware стали доступны по отдельности: `install_session_gate(app)` можно
вызвать на голом `FastAPI()`, а `inspect.getsource` читает конкретную
фабрику, а не 310-строчное тело `create_app`. Регрессия-тест дедлока
connection pool (`test_session_gate_dispatches_its_database_lookup_to_a_thread`)
переписан на `edge.middleware.install_session_gate` — проверяет тот же
инвариант, но по коду, который теперь owns this middleware.

### Правило, без которого тихо ломаются 17 тестов

`edge/*` читает конфигурацию **через объект модуля** (`config.RATE_LIMIT_*`),
а не импортом по значению. Причина: `monkeypatch.setattr(main, "ALLOWED_HOSTS", ...)`
патчил атрибут `main`, потому что `main` импортировал имя из `config` на
уровне модуля. Патч на `config` работает для всех потребителей сразу и
заодно чинит рассинхрон между `main` и `config`, который существовал и до
переезда.

| Тест | Было | Стало |
|---|---|---|
| `test_stage7_frontend_config.py` | `main.ALLOWED_HOSTS`, `main._origin_allowed` | `config.ALLOWED_HOSTS`, `origin_guard._origin_allowed` |
| `test_stage8_coexistence.py` | `main.HSTS_MAX_AGE`, `main.FRONTEND_DIST_DIR`, `main.lifespan` | `config.HSTS_MAX_AGE`, `path_config.FRONTEND_DIST_DIR`, `edge.lifespan.lifespan` |
| `test_stage9_limits_capacity.py` | `main.RATE_LIMIT_*` | `config.RATE_LIMIT_*` |
| `test_stage10_turnstile.py` | `main._build_content_security_policy` | `security._build_content_security_policy` |

### Инварианты, проверенные после переезда

1. **Порядок middleware сохранён.** Starlette выполняет последний
   зарегистрированный внешним, поэтому порядок вызовов в `create_app`
   (throttle → session gate → CORS → Host/Origin guard → security headers)
   и есть порядок выполнения. Он зафиксирован в docstring `edge/middleware.py`
   с явным «не переставлять».
2. **Ленивые импорты не подняты наверх.** `background_sync` (в `lifespan`),
   `hosted_auth` (в `main.create_app` и в `install_session_gate`), `proxy`
   грузятся внутри функций — иначе `test_hosted_startup_imports_no_desktop_module`
   в подпроцессе падает.
3. **OpenAPI не сдвинулся.** `tests/test_api_contract.py` зелёный: те же 41
   desktop-операция + 4 hosted-only, те же `operationId`.
4. `edge/` добавлен в `known-first-party` в `ruff.toml` (иначе isort роняет
   `from edge import …` в группу third-party).

---

## 7. Этап 3 — доменные пакеты ✅ выполнен

Порядок переездов: `core/` → `gapi/` → `db/` → `schemas/` → `feedback/` →
`auth/` → `sync/`. Он обратный топологическому: сначала то, что ни от кого не
зависит, чтобы у каждого шага менялось минимальное число файлов.

### 7.1 Правило переезда

**1 файл → 1 модуль, без склейки и разделения**, иначе рвутся `monkeypatch`-цели.
Разделение (§7.5) — отдельный коммит после переезда.

`auth.py` → `auth/desktop.py` переезжает атомарно, и только потом
`api/identity.py` → `auth/identity.py`: пока в корне лежит `auth.py`, создать
каталог `auth/` нельзя — имя уже занято модулем.

Проверено на Python 3.13: если рядом лежат и `sync.py`, и каталог `sync/`,
побеждает **пакет** (проверено: `import sync` → `sync/__init__.py`). Для
`auth.py` + каталог `auth/` **без** `__init__.py` побеждает **модуль**. Оба
исхода ломают импорт молча, поэтому `__init__.py` создаётся в том же коммите,
что и переезд.

### 7.2 Карта переездов

| Сейчас | Станет | Строк | Кого тянет за собой |
|---|---|---|---|
| `config.py` | `core/config.py` + `core/origins.py` | 548 | 26 модулей, 8 тестов, `tools/classroom_smoke.py` |
| `access_log.py` | `core/logging_filters.py` | 131 | `main`, `edge/lifespan`, `sync_worker`, 2 теста |
| `metrics.py` | `core/metrics.py` | 79 | 7 модулей, 2 теста |
| `rate_limit.py` | `core/rate_limit.py` | 86 | `main`, 1 тест |
| `capacity.py` | `core/capacity.py` | 128 | 1 тест |
| `token_crypto.py` | `core/crypto.py` | 84 | `google_credentials`, `tools/generate_hosted_secrets.py` |
| `proxy.py` | `core/proxy.py` | 144 | `edge/middleware`, `edge/origin_guard`, `hosted_auth`, 2 теста |
| `classroom_api.py` | `gapi/classroom.py` | 406 | `api/identity`, `sync_service`, `sync_store`, 3 теста |
| `google_credentials.py` | `gapi/credentials.py` | 327 | `hosted_auth`, `sync_service`, 6 тестов |
| `oauth_transport.py` | `gapi/oauth_transport.py` | 170 | `auth`, `gapi/credentials`, 3 теста, `tools/classroom_smoke.py` |
| `database.py` | `db/session.py` | 158 | 30 модулей, 9 тестов, `migrations/env.py` |
| `models.py` | `db/models/classroom.py` | 271 | 22 модуля, 11 тестов |
| `models_auth.py` | `db/models/accounts.py` | 145 | 27 модулей, 15 тестов |
| `models_feedback.py` | `db/models/feedback.py` | 149 | 6 модулей, 4 теста |
| `models_admin.py` | `db/models/admins.py` | 43 | 4 модуля, 3 теста |
| `schemas.py` | `schemas/dashboard.py` | 284 | 10 модулей в `api/` |
| `schemas_feedback.py` | `schemas/feedback.py` | 265 | 2 модуля |
| `schemas_admins.py` | `schemas/admins.py` | 91 | `admins_api` |
| `feedback_service.py` | `feedback/service.py` | 260 | 3 модуля, 1 тест |
| `feedback_attachments.py` | `feedback/attachments.py` | 383 | 5 модулей, 3 теста |
| `auth.py` | `auth/desktop.py` | 389 | 5 модулей, 4 теста, `tools/check_oauth_flow.py` |
| `ownership.py` | `auth/ownership.py` | 99 | 12 модулей, 7 тестов |
| `admin_auth.py` | `auth/roles.py` | 166 | 3 модуля, 1 тест |
| `hosted_auth.py` | `auth/hosted.py` | 668 | 15 модулей, 11 тестов |
| `api/identity.py` | `auth/identity.py` | 165 | 2 модуля, 3 теста |
| `sync.py` | `sync/__init__.py` (фасад) | 42 | 7 модулей, 2 теста |
| `sync_store.py` | `sync/store.py` | 721 | 12 модулей, 13 тестов |
| `sync_service.py` | `sync/service.py` | 651 | 6 модулей, 7 тестов |
| `sync_scheduler.py` | `sync/scheduler.py` | 451 | 4 модуля, 3 теста |
| `sync_worker.py` | `sync/worker.py` | 186 | `edge/lifespan`, `auth/desktop`, compose |
| `background_sync.py` | `sync/background.py` | 78 | `edge/lifespan`, `launcher`, `auth/desktop` |
| `grading.py` | `sync/grading.py` | 58 | `api/queries/*` |

### 7.3 Что правится в том же коммите

* `migrations/env.py:26-31` — `import models*` → `from db.models import …`,
  `from database import Base` → `from db.session import Base`.
* `db/session.py::_import_models` (строки 109–131) — тот же список моделей.
* `compose.yml:125` и `compose.local.yml:119` — `python sync_worker.py` →
  `python -m sync.worker`. Флаг `-m` обязателен: при прямом запуске файла
  каталог `backend/` не попадает первым в `sys.path`, и плоские импорты падают.
* `compose.local.yml:123` и `Dockerfile:10` — комментарии с путём.
* `tools/dump_openapi.py:27`, `tools/classroom_smoke.py:28-30`,
  `tools/check_oauth_flow.py:39`, `tools/generate_hosted_secrets.py:26`.
* `ruff.toml` — в `known-first-party` добавляются `core`, `db`, `gapi`,
  `feedback`, `schemas`; старые имена (`access_log`, `classroom_api`,
  `config`, `database`, `models*`, `schemas*`, `token_crypto`, …) убираются.
* `docs/BACKEND_STRUCTURE.md` и `ADR-0039` — карта слоёв и имя `gapi/`.

### 7.4 Цели `monkeypatch` — переезжают вместе с кодом

Полный список снят регуляркой по `tests/` (16 модулей, 34 цели). Ни одна
строка не может остаться со старым именем модуля: иначе `monkeypatch.setattr`
создаст атрибут на модуле, который никто не импортирует, и тест пройдёт мимо
проверки.

| Старая цель | Новая цель | Тесты |
|---|---|---|
| `config.*` (10 констант) | `core.config.*` | 8 файлов |
| `database.HOSTED_MODE`, `database.SessionLocal` | `db.session.*` | `test_admin_roles`, `test_stage10_part1`, `test_user_isolation` |
| `hosted_auth.COOKIE_SECURE`, `.TURNSTILE_*`, `._fetch_identity`, `._verify_turnstile`, `.httplib2.Http` | `auth.hosted.*` | `test_hosted_auth`, `test_stage10_turnstile`, `test_stage7_frontend_config` |
| `google_credentials.get_google_credentials`, `.refresh_google_credentials` | `gapi.credentials.*` | 5 файлов |
| `oauth_transport.post_token_request`, `.refresh_credentials` | `gapi.oauth_transport.*` | `test_hosted_auth`, `test_sync_restart`, `test_stage9_limits_capacity` |
| `sync_service.*` (6 символов) | `sync.service.*` | `test_stage9_limits_capacity`, `test_sync_*` |
| `sync_store.*` | `sync.store.*` | 8 файлов |
| `sync_scheduler.run_user` | `sync.scheduler.run_user` | `test_stage9_limits_capacity` |
| `sync_worker.init_db`, `.select_due_users`, `.sync_users` | `sync.worker.*` | `test_sync_scheduler` |
| `sync.sync_now` | `sync.sync_now` (фасад) | `test_stage9_limits_capacity` |
| `identity.*` | `auth.identity.*` | `test_user_isolation`, `test_stage9_limits_capacity`, `test_teacher_mode` |
| `attachments.FEEDBACK_MAX_*` | `feedback.attachments.FEEDBACK_MAX_*` | `test_feedback_attachments` |
| `feedback_service.FEEDBACK_*` | `feedback.service.FEEDBACK_*` | `test_feedback_tickets` |
| `auth.get_valid_credentials` | `auth.desktop.get_valid_credentials` | 4 файла |
| `proxy.ALLOWED_HOSTS`, `.TRUSTED_PROXIES`, `.peer_is_trusted_proxy` | `core.proxy.*` | `test_stage7_frontend_config`, `test_stage10_part1` |
| `path_config.*` | без изменений | 2 файла |

Тонкость, которую легко пропустить: `hosted_auth` импортирует `COOKIE_SECURE`
и `TURNSTILE_*` **по значению** (`from config import …`, строки 68–73), и
`proxy` так же импортирует `ALLOWED_HOSTS`/`TRUSTED_PROXIES`. Тесты патчат
**эти** имена в `hosted_auth`/`proxy`, а не в `config`. После переезда в
`core/` правило «читать конфигурацию через объект модуля» (§6) требует
заменить такие импорты на `core.config.X` — иначе патч на `core.config`
перестанет видеть значение. Это единственное место Этапа 3, где меняется не
имя модуля, а способ чтения.

### 7.5 Дробление остаточных толстяков ✅ выполнено

Деление шло **по назначению**, а не по числу строк: файл, который решает два
разных вопроса, делится на два; файл, который решает один, но дорос, — нет.

| Модуль | Было | Стало | Граница |
|---|---|---|---|
| `core/config.py` | 548 | `core/config.py` + `core/origins.py` + `core/http_config.py` | нормализация origin/host — чистые функции без окружения; HTTP-поверхность (hosts, CORS, cookies, HSTS, Turnstile) читается почти исключительно краем |
| `sync/store.py` | 721 | `sync/store/{status,cache,writing}.py` + фасад | переходы статуса · чтение двух таблиц и purge · перевод payload → строки |
| `sync/service.py` | 651 | `sync/service/{_fetch,_fetching,results,common}.py` + фасад | claim и права · fan-out к Google · транзакция записи · коды исходов и политика ошибок |
| `sync/scheduler.py` | 451 | `sync/scheduler/{due,_scan}.py` + фасад | арифметика времени (stagger, backoff, due-запрос) · класс и пул |
| `auth/hosted.py` | 668 | `auth/hosted/{sessions,turnstile}.py` + `__init__.py` | сессия — отдельный механизм от OAuth-раундтрипа · Turnstile опционален и держит единственный секрет |
| `gapi/classroom.py` | 406 | `gapi/timeparse.py` | три формата дат Google — чистый парсинг без клиента |
| `api/routes/feedback_admin.py` | 423 | `admin_shapes.py` + роуты | админ-проекция тикета: тест фиксирует, что полезная выгрузка не содержит этих полей |
| `api/routes/feedback.py` | 353 | `feedback_shapes.py` + роуты | проекция владельца и общий 422 |

Два деления оказались неочевидными и стоили отдельной правки:

* **Получение и запись падают по-разному.** Fan-out к Google медленный, сетевой и
  повторяемый; транзакция записи короткая и повторяться не должна. В одном файле
  на 651 строку это различие не читалось.
* **Локальная переменная `due` затенила модуль `due`.** `scan_once` называл
  список пользователей `due` — тем же именем, что и новый модуль. Тест падал с
  `AttributeError: 'list' object has no attribute 'run_user'`. Список переименован
  в `due_ids`: имена, совпадающие с именами модулей, — это ловушка, а не
  экономия символов.

### 7.6 Проверка после каждого переезда

1. `python -m pytest` — зелёный, число тестов не уменьшилось (было 483, стало
   491: +18 структурных проверок Этапа 4).
2. `python tools/dump_openapi.py` — diff с закоммиченным `frontend/openapi.json`
   пуст.
3. `ruff check backend` — чисто.
4. `grep -rn "from <старое_имя> import" backend tests tools migrations` — пусто,
   кроме `path_config` и `launcher` (ADR-0016).

---

## 8. Этап 4 — ограждения ✅ выполнен

`tests/test_backend_structure.py` — 18 тестов, читающих исходники через `ast`
(правило, которое матчится внутри докстринга, кричит «ложно» и потому первым
удаляется):

1. **Бюджет строк.** Ни один модуль в `backend/**` не длиннее лимита своей
   категории (`api/routes` 280, `api/queries` 350, `main.py` 200, остальное 400;
   фасад — 60). На старте было 8 нарушителей: `sync_store.py` (721),
   `hosted_auth.py` (668), `sync_service.py` (651), `launcher.py` (564),
   `config.py` (548), `sync_scheduler.py` (451), `feedback_admin_api.py` (423),
   `classroom_api.py` (406). Из них один остался **по решению**: `launcher.py` —
   Nuitka entry (ADR-0016), он в списке `BUDGET_EXEMPT`, и отдельный тест
   требует, чтобы этот список оставался одноэлементным.
2. **Чистота ядра.** `core/**` не импортируют фреймворки и хранилища
   (`fastapi`, `starlette`, `pydantic`, `sqlalchemy`, `alembic`, `googleapiclient`,
   `google_auth_*`, `httplib2`). Исключение — `core/proxy.py`: HTTP-решение само
   по себе принимает `Request` как вход, это не утечка. Стандартная библиотека
   разрешена: `config` читает `os.environ`, `metrics` — `logging`.
3. **Чистый домен.** `sync/grading.py` не имеет импортов вовсе, кроме
   `datetime`. Иначе порт на другой язык перестаёт быть возможным, и это
   свойство становится невидимым в тот момент, когда модуль обрастает.
4. **Чистота запросов.** `api/queries/**` не импортируют `fastapi`/`starlette`.
5. **Чистота роутов.** `api/routes/**` не импортируют `gapi*` и писателей кэша.
6. **Локальный импорт остаётся локальным.** `api/routes/sync.py` читает
   `sync.store.sync_status` внутри функции — второе честное исключение из
   `docs/BACKEND_STRUCTURE.md`. Отдельный тест падает, если импорт поднимется на
   уровень модуля.
7. **Корень `backend/` без долгов.** В корне только `main.py`, `launcher.py`,
   `path_config.py`, `build_secrets.py`, `maintenance.py`, `embedded_secrets.py`.
8. **Слои не затеняют пакеты.** `backend/` — корень `sys.path`, поэтому имя слоя
   конфликтует с `site-packages`. `find_spec` молча проходит на PEP 420, так что
   проверка делает настоящий импорт и сверяет, что `__file__` лежит внутри
   `backend/`.

Плюс:

* **`ruff.toml`** — `flake8-tidy-imports.banned-api` с двумя кодами:
  `SIBLING_NAME_IMPORT` (прямой импорт имени из соседнего модуля пакета — ломает
  `monkeypatch`, §5) и `STAR_IMPORT`. Список намеренно узкий: только те модули,
  чьи функции патчит суита. Константа (`from core.config import HOSTED_MODE`) в
  список не входит — тесты патчат `core.config.X`, и копия безвредна; запрет
  лишних случаев приучает игнорировать правило.
* **CI** — джоб `pyright` (`npx pyright@1.1.414 --project pyrightconfig.json`)
  рядом с `ruff check backend` и `pytest`. Pyright ловит то, чего не видит ruff:
  реэкспорт, указывающий не на тот модуль.
* **`README.md`** — раздел «Структура `backend/`» со ссылкой на
  `docs/BACKEND_STRUCTURE.md` и на этот план.
* **`docs/BACKEND_STRUCTURE.md`** — карта слоёв, «почему `gapi/`, а не
  `google/`», разбивка по внутренним пакетам и обновлённые бюджеты.

## 9. Что не трогаем ни в одном этапе

`path_config.py` и `launcher.py` (Nuitka, ADR-0016), `credentials.json`,
`build.bat`, `pytest.ini`, `Dockerfile CMD`, HTTP-контракт. `backend/` остаётся
корнем `sys.path` — поэтому 8 мест с `sys.path.insert`/`pythonpath` не требуют
изменений.

Одно исключение внутри этого этапа: **compose-файлы меняются в Этапе 3** —
`python sync_worker.py` → `python -m sync.worker` (§7.3). Это не «compose не
трогаем», а смена способа запуска того же worker'а.

---

## 10. Риски и откат

| Риск | Что делаем |
|---|---|
| Тихая смена API при переносе | `tests/test_api_contract.py` + сравнение `dump_openapi.py` с закоммиченным `frontend/openapi.json` |
| Циклы импортов при разделении | `auth/identity.py` импортируется из `auth/hosted.py` лениво, как сейчас |
| Двойной импорт модуля (module vs package) | переезд атомарный в одном коммите, шимы-реэкспорты не оставляем (§7.1) |
| **Слой перекрыл PyPI-пакет** | имя слоя проверено `find_spec` до переезда; `gapi/` вместо `google/` (§3.1) |
| **Worker не стартует после переезда** | `python -m sync.worker` в обоих compose; проверяется реальным запуском, не только тестом |
| **Патч уехал в мёртвый модуль** | §7.4 — цели `monkeypatch` переезжают вместе с кодом, иначе тест зеленеет вхолостую |
| Сломалась desktop-сборка | `path_config.py` / `launcher.py` не трогаем |
| Тесты «починили» ослаблением | `pytest` обязан быть зелёным с тем же числом тестов |

**Откат:** каждый этап — отдельный коммит, откат — `git revert` этого коммита.
Реверт работает и для модуля, и для пакета: файлы просто возвращаются на место,
никакой «разрегистрации» в `sys.path` не требуется.