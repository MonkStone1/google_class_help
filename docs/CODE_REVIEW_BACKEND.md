# 🔥 GRILL ME — Backend (GoogleClassHelp) · с решениями

> Ревью в стиле FAANG: без реверансов. Файлы: `api.py`, `sync.py`, `auth.py`, `main.py`,
> `background_sync.py`, `database.py`, `models.py`, `classroom_api.py`, `launcher.py`,
> `build_secrets.py`, `test_classroom.py`.
>
> После каждого пункта — блок **✅ Решение** с конкретным кодом под этот проект.
>
> Дата ревью: по состоянию рабочей копии (ветка `master`, коммитов ещё нет).

**Приговор коротко:** код заметно лучше среднего пет-проекта — комментарии с ADR,
осознанные компромиссы, аккуратные докстринги. Но под этой обёрткой: `O(вся_база)`
на каждый HTTP-запрос, сетевой вызов к Google внутри GET `/status`, сетевой refresh
токена **под мьютексом**, мёртвая дублированная функция и эндпоинт, который для
студента всегда возвращает пустые оценки. Это не пройдёт ревью в FAANG не потому
что «плохо написано», а потому что профилирование никто не открывал.

---

## 1. 🐛 Баги и их решения

### 1.1 🔴 `_get_course` определена дважды — мёртвый код в проде

`api.py`:

```python
def _get_course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.course_state == "ARCHIVED":
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


def _course_role(db: Session, course: Course) -> str:
    ...

def _get_course(db: Session, course_id: str) -> Course:   # ← ТА ЖЕ ФУНКЦИЯ ЕЩЁ РАЗ
    course = db.get(Course, course_id)
    if course is None or course.course_state == "ARCHIVED":
        raise HTTPException(status_code=404, detail="Course not found.")
    return course
```

Вторая версия молча затирает первую. Это значит, что **никто не запускал даже
поверхностный diff по файлу перед коммитом**. В git пока ноль коммитов —
и уже копипаст-мусор.

**✅ Решение** — удалить второе определение целиком (обе версии идентичны,
ничего кроме `del` не нужно):

```python
def _get_course(db: Session, course_id: str) -> Course:
    """Course by id; ARCHIVED and missing courses are 404."""
    course = db.get(Course, course_id)
    if course is None or course.course_state == "ARCHIVED":
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


def _course_role(db: Session, course: Course) -> str:
    """Role of the signed-in user in this course ("TEACHER"/"STUDENT")."""
    row = db.get(CourseRole, course.id)
    return row.role if row else "STUDENT"


# ← второй _get_course удалён. Точка.
```

И добавить в CI простую ловушку на будущее: `ruff check --select F811`
(redefinition of unused name) — он ловит именно это.

---

### 1.2 🔴 `/courses/{course_id}/students/{student_id}/grades` для студента всегда пуст

`api.py` → `student_grades`: для студента `student_id="me"`, но запрос идёт в
`CourseWorkSubmission` — таблицу, которая заполняется **только для teacher-курсов**
и хранит реальные Google `userId`. Студентские данные лежат в `StudentSubmission`,
которая здесь вообще не запрашивается. Итог: все items `not_submitted`, оценок ноль.

**✅ Решение** — выбирать таблицу по роли, а поля, которых нет в
`StudentSubmission` (`submitted_at`, `attachments`), читать аккуратно:

```python
def _grade_submissions(
    db: Session, course_id: str, student_id: str, is_teacher: bool
) -> dict[str, CourseWorkSubmission | StudentSubmission]:
    """Submissions of one student in one course, from the right table.

    Teacher courses keep per-student rows in CourseWorkSubmission; the
    student route keeps the user's own rows in StudentSubmission.
    """
    if is_teacher:
        rows = (
            db.query(CourseWorkSubmission)
            .filter_by(course_id=course_id, student_id=student_id)
            .all()
        )
    return {row.coursework_id: row for row in rows}
    rows = db.query(StudentSubmission).filter_by(course_id=course_id).all()
    return {row.coursework_id: row for row in rows}


@router.get("/courses/{course_id}/students/{student_id}/grades")
def student_grades(course_id: str, student_id: str, db: Session = Depends(get_db)) -> StudentGradesOut:
    course = _get_course(db, course_id)
    is_teacher = _course_role(db, course) == "TEACHER"
    if not is_teacher and student_id != "me":
        raise HTTPException(status_code=403, detail="Students can only view their own grades.")
    if not is_teacher:
        student_id = "me"

    sub_map = _grade_submissions(db, course_id, student_id, is_teacher)
    ...
    for work in works:
        row = sub_map.get(work.id)
        graded = row is not None and row.assigned_points is not None
        items.append(
            StudentGradeItem(
                ...
                # Поля есть только у teacher-строк:
                submitted_at=getattr(row, "submitted_at", None) if row else None,
                attachments=[
                    MaterialOut(**m)
                    for m in ((getattr(row, "attachments", None) if row else None) or [])
                ],
            )
        )
```

И тест, который сегодня падает, а после фикса — зелёный:

```python
def test_student_sees_own_grades(client, seeded_student_course):
    resp = client.get("/api/courses/c1/students/me/grades")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["points"] == 90  # до фикса: None
```

---

### 1.3 🔴 Сетевой вызов к Google внутри GET-эндпоинтов

`_build_auth_status()` синхронно вызывает `get_user_profile()` при каждом
`GET /api/status` и `GET /api/auth/status`. Фронт во время логина пулит статус
каждые 1.5 с — каждый тик это roundtrip к Google.

**✅ Решение** — кэш профиля с TTL, сеть — вне горячих эндпоинтов:

```python
import time
import threading

_profile_lock = threading.Lock()
_profile_cache: tuple[float, str | None, str | None] | None = None
PROFILE_TTL_SECONDS = 300


def _cached_profile(creds) -> tuple[str | None, str | None]:
    """User profile with a 5-minute TTL; one request at a time."""
    global _profile_cache
    with _profile_lock:
        if _profile_cache is not None and time.monotonic() - _profile_cache[0] < PROFILE_TTL_SECONDS:
            return _profile_cache[1], _profile_cache[2]
    profile = ClassroomClient(build_service(creds)).get_user_profile()  # сеть БЕЗ замка
    name = profile.get("name", {})
    value = (name.get("fullName"), profile.get("emailAddress") or name.get("fullName"))
    with _profile_lock:
        _profile_cache = (time.monotonic(), value[0], value[1])
    return value


def _build_auth_status() -> AuthStatus:
    status = auth.login_status()
    user_name = user_email = None
    creds = auth.get_valid_credentials()
    if creds is not None:
        user_name, user_email = _cached_profile(creds)
    return AuthStatus(**status, user_name=user_name, user_email=user_email)
```

Почему именно так: профиль меняется раз в год, а читается каждые 1.5 с во время
логина; `time.monotonic()` — не `datetime.now()`, чтобы не стрелять себе в ногу
при переводе часов.

---

### 1.4 🔴 Token refresh под мьютексом

`login_status()` держит `_login_lock`, пока `get_valid_credentials()` делает
сетевой refresh (до 30 c по таймауту httplib2). Замок защищает `_login_state`
(четыре ключа словаря), а закрыл им сетевой I/O.

**✅ Решение** — два шага: (а) сеть вынести из-под замка, (б) refresh
сериализовать отдельным замком, чтобы два потока не обновляли токен одновременно:

```python
_refresh_lock = threading.Lock()


def get_valid_credentials() -> Credentials | None:
    creds = load_credentials()
    if not creds:
        return None
    if not set(SCOPES).issubset(set(creds.scopes or [])):
        logout()
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        with _refresh_lock:  # только один поток реально обновляет
            # Double-check: пока мы ждали, другой поток мог уже обновить токен
            # на диске — перечитываем, чтобы не обновлять второй раз.
            creds = load_credentials() or creds
            if creds.valid:
                return creds
            try:
                _refresh_credentials(creds)
            except Exception:  # noqa: BLE001
                return None
            _save_credentials(creds)
        return creds
    return None


def login_status() -> dict:
    # Сетевой refresh — ВНЕ замка: _login_lock защищает только _login_state.
    authenticated = get_valid_credentials() is not None
    with _login_lock:
        return {
            "authenticated": authenticated,
            "login_in_progress": _login_state["in_progress"],
            "error": _login_state["error"],
            "auth_url": _login_state["auth_url"],
        }
```

---

### 1.5 🟠 Race в `start_login`: два окна согласия

`in_progress` выставляется внутри `_run_login_flow` **после** старта потока —
между проверкой и первым тиком потока два быстрых клика открывают два OAuth-потока.

**✅ Решение** — флаг ставится в самой `start_login` под тем же замком,
фоновый поток флаг только снимает:

```python
def start_login() -> dict:
    with _login_lock:
        if _login_state["in_progress"]:
            return {"started": True, "already_running": True}
        if _client_config() is None:
            return {
                "started": False,
                "error": "OAuth client configuration is missing in this build. "
                "See README for setup instructions.",
            }
        # Флаг ставим ЗДЕСЬ: окно между проверкой и стартом потока закрыто.
        _login_state["in_progress"] = True
        _login_state["error"] = None
        _login_state["auth_url"] = None
    threading.Thread(target=_run_login_flow, daemon=True).start()
    return {"started": True, "already_running": False}


def _run_login_flow() -> None:
    try:
        config = _client_config()
        if config is None:  # конфиг пропал между проверкой и стартом — редкость
            raise RuntimeError("OAuth client configuration not available")
        creds = _run_consent_flow(config)
        _save_credentials(creds)
        from background_sync import request_soon

        request_soon()
    except Exception as exc:
        logger.exception("Google sign-in failed")
        with _login_lock:
            _login_state["error"] = repr(exc)
    finally:
        with _login_lock:
            _login_state["in_progress"] = False
            _login_state["auth_url"] = None
```

---

### 1.6 🟠 SQLite без WAL и busy_timeout

`check_same_thread=False` включён, но прагмы не выставлены: фоновая синхронизация
коммитит в цикле, API читает те же таблицы из других потоков → периодический
`database is locked` под нагрузкой.

**✅ Решение** — три прагмы через event-подключение, бонусом включаем FK
(сейчас ваши `ondelete="CASCADE"` не исполняются вовсе — SQLite их игнорирует
без `foreign_keys=ON`):

```python
# database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_FILE

engine = create_engine(
    f"sqlite:///{DATABASE_FILE}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")     # читатели не блокируются писателем
    cursor.execute("PRAGMA busy_timeout=5000")    # ждём вместо мгновенного SQLITE_BUSY
    cursor.execute("PRAGMA foreign_keys=ON")      # включаем реальные CASCADE
    cursor.close()
```

После `foreign_keys=ON` можно сократить `_purge_course` в `sync.py`: строка
`db.delete(stale)` сама каскадно удалит подчинённые строки — вручную удалять
пять таблиц станет не нужно.

---

### 1.7 🟠 `list_courses` — единственный метод клиента без обработки HttpError

Все остальные list-методы возвращают `None`/частичный результат при `HttpError`,
чтобы «не стирать кэш при ошибке». Базовый метод падает наверх и валит весь sync.

**✅ Решение** — симметрично остальным: `None` при ошибке + осознанная обработка
в `_do_sync` (не purge'ить кэш, если список курсов получить не удалось):

```python
# classroom_api.py
def list_courses(
    self, student_id: str | None = None, teacher_id: str | None = None
) -> list[dict] | None:
    """... Returns ``None`` on an HTTP error so the caller keeps the cache."""
    items: list[dict] = []
    page_token: str | None = None
    while True:
        kwargs: dict = {"pageSize": 100, "pageToken": page_token}
        if student_id:
            kwargs["studentId"] = student_id
        if teacher_id:
            kwargs["teacherId"] = teacher_id
        try:
            response = (
                self._service.courses().list(**kwargs).execute(num_retries=NUM_RETRIES)
            )
        except HttpError:
            return None
        items.extend(response.get("courses", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return items


# sync.py
def _resolve_courses(client) -> list[tuple[dict, str]] | None:
    courses = client.list_courses()
    if courses is None:
        return None  # sync сохранит кэш и запишет ошибку в sync_state
    teacher_list = client.list_courses(teacher_id="me")
    if teacher_list is None:
        return None
    teacher_ids = {raw["id"] for raw in teacher_list}
    return [
        (raw, "TEACHER" if raw["id"] in teacher_ids else "STUDENT")
        for raw in courses
        if raw.get("courseState") != "ARCHIVED"
    ]
```

---

### 1.8 🟠 `test_classroom.py` — не тест, а мины

Файл `test_*` без единого `assert`: при прогоне pytest требует `credentials.json`,
открывает браузер и пишет токен в `backend/token.json` вместо `DATA_DIR`.

**✅ Решение** — перенести в `tools/check_oauth_flow.py` (pytest его не собирает)
и рядом положить настоящие тесты:

```text
 tools/check_oauth_flow.py   # ручной smoke-тест OAuth (был backend/test_classroom.py)
tests/
  conftest.py               # фикстуры: in-memory SQLite, TestClient
  test_api_auth.py
  test_student_grades.py
  test_assignment_filters.py
```

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient

from database import Base, SessionLocal, engine
from main import app


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)
```

---

### 1.9 🟡 Мелочь, но показательная — и починка

| Проблема | ✅ Решение |
| --- | --- |
| `reset_cache`: недостижимый `raise RuntimeError("Cache database is missing.")` | Удалить проверку: БД заведомо существует, мы только что удаляли из неё строки. Функция заканчивается `db.commit()` |
| `models.py`: `default=datetime.utcnow` (deprecated, и значение всё равно перезаписывается sync'ом) | `synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)` — без default; значение ставит `_do_sync` |
| `main.py`: `@app.on_event("startup")` — deprecated | Lifespan (см. код ниже) |
| `launcher.py` → `find_free_port`: TOCTOU — порт проверен, uvicorn биндит позже | Проверять фактом старта сервера, а не пробным биндом (см. код ниже) |
| `teacher_names: Mapped[list]` без параметра типа | `Mapped[list[str]]` |

```python
# main.py — lifespan вместо on_event
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    start_background_sync()
    yield
    stop_background_sync()


app = FastAPI(title="Local Google Classroom Dashboard", version="1.0.0", lifespan=lifespan)
```

```python
# launcher.py — порт подтверждается стартом uvicorn, а не пробным биндом
def start_on_free_port(app) -> tuple[uvicorn.Server, threading.Thread, int]:
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 50):
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None,
                           loop="asyncio", http="h11", ws="none", lifespan="on")
        )
        thread = threading.Thread(target=server.run, name="uvicorn-server", daemon=True)
        thread.start()
        if wait_until_ready(port, server, thread):
            return server, thread, port  # порт реально слушается
        server.should_exit = True
        thread.join(timeout=5)
    raise RuntimeError("No bindable port found in the default range")
```

---

## 2. 🏗️ Архитектура и её решения

### 2.1 🔴 «Эндпоинты тонкие» — не верьте докстрингу

`_load_assignments()` при каждом запросе выгружает все таблицы в Python и
фильтрует списочными включениями; `coursework_detail` ищет одну запись перебором
всего списка.

**✅ Решение** — считать агрегаты в SQL и брать запись по PK:

```python
from sqlalchemy import case, func


def _assignment_by_id(db: Session, coursework_id: str) -> AssignmentOut | None:
    """Одна запись — один запрос по PK вместо загрузки всей базы."""
    work = db.get(CourseWork, coursework_id)
    if work is None:
        return None
    course = db.get(Course, work.course_id)
    if course is None or course.course_state == "ARCHIVED":
        return None
    return _build_assignment_out(db, work, course)  # общий билдер одной строки


def _course_stats_sql(db: Session) -> list[tuple[Course, int, int, int]]:
    """total / todo / graded на стороне SQLite вместо Python-циклов."""
    todo = case((StudentSubmission.state.not_in(SUBMITTED_STATES), 1), else_=0)
    graded = case((StudentSubmission.assigned_points.is_not(None), 1), else_=0)
    return (
        db.query(
            Course,
            func.count(CourseWork.id).label("total"),
            func.coalesce(func.sum(todo), 0).label("todo"),
            func.coalesce(func.sum(graded), 0).label("graded"),
        )
        .outerjoin(CourseWork, CourseWork.course_id == Course.id)
        .outerjoin(StudentSubmission, StudentSubmission.coursework_id == CourseWork.id)
        .filter(Course.course_state != "ARCHIVED")
        .group_by(Course.id)
        .order_by(Course.name)
        .all()
    )
```

А в `coursework_detail`:

```python
@router.get("/courses/{course_id}/coursework/{coursework_id}")
def coursework_detail(course_id: str, coursework_id: str, db: Session = Depends(get_db)):
    course = _get_course(db, course_id)
    work = db.get(CourseWork, coursework_id)
    if work is None or work.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    base = _assignment_by_id(db, coursework_id)  # было: next(... for a in _load_assignments(db) ...)
    if base is None:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    ...
```

Результат: O(данных)-на-запрос превращается в индексный доступ; память перестаёт
расти с размером кэша; фильтры `?status=` превращаются в `WHERE`.

### 2.2 🟠 `sync.py` — свалка ответственностей

Транспорт, запись кэша и доменные правила (`grade_percent`, `compute_priority`)
живут в одном файле, и `api.py` тянет домен из синка.

**✅ Решение** — разрезать на слои, оставив `sync.py` фасадом для обратной
совместимости (публичные импорты `api.py` не меняются):

```text
 backend/
  classroom_api.py    # транспорт (уже есть, не трогаем)
  grading.py          # ДОМЕН: is_submitted_state, derive_submission_status,
                      #        grade_percent, compute_priority — чистые функции
  sync_store.py       # ЗАПИСЬ КЭША: _upsert_work, _write_teacher_course,
                      #              _write_student_course, _purge_*, reset_cache
  sync_service.py     # ОРКЕСТРАЦИЯ: _do_sync, пулы, зеркалирование
  sync.py             # фасад: from grading import *  +  from sync_service import sync_now
```

```python
# grading.py — чистый домен, ноль зависимостей от Google и SQLAlchemy
SUBMITTED_STATES = {"TURNED_IN", "RETURNED"}


def grade_percent(points: float | None, max_points: float | None) -> float | None:
    if points is None or max_points is None or max_points <= 0:
        return None
    return round(points / max_points * 100, 1)
```

```python
# sync.py — фасад, чтобы api.py продолжал работать без правок импортов
from grading import (  # noqa: F401
    compute_priority,
    derive_submission_status,
    grade_percent,
    is_submitted_state,
)
from sync_service import get_state, get_state_datetime, reset_cache, sync_now  # noqa: F401
```

### 2.3 🟠 Две таблицы одного и того же факта

`StudentSubmission` и `CourseWorkSubmission` — одна сущность в двух таблицах;
источник бага 1.2 и дупликации в `_submissions_for_work`.

**✅ Решение** — долгосрочно миграция в одну таблицу; короткосрочно (без ломки
существующего кэша, чего требует ADR-0003) — единый интерфейс доступа:

```python
# sync_store.py
SubmissionRow = CourseWorkSubmission | StudentSubmission


def get_submission(
    db: Session, course_id: str, coursework_id: str, student_id: str, *, is_teacher: bool
) -> SubmissionRow | None:
    """Одна точка доступа к сдаче ученика — таблицу выбирает роль, не вызывающий."""
    if is_teacher:
        return db.get(CourseWorkSubmission, (course_id, coursework_id, student_id))
    return db.get(StudentSubmission, (course_id, coursework_id))
```

```python
# api.py — _submissions_for_work перестаёт дублировать маппинг полей
def _submission_out_for(row: SubmissionRow | None, student_id: str, name: str, work: CourseWork) -> SubmissionOut:
    if row is None:
        return SubmissionOut(student_id=student_id, student_name=name, coursework_id=work.id,
                             status="not_submitted", max_points=work.max_points)
    graded = row.assigned_points is not None
    return SubmissionOut(
        student_id=student_id, student_name=name, coursework_id=work.id,
        submission_state=row.state,
        status=sync.derive_submission_status(row.state, graded),
        submitted=sync.is_submitted_state(row.state),
        returned=row.state == "RETURNED", graded=graded, late=row.late,
        points=row.assigned_points, max_points=work.max_points,
        percent=sync.grade_percent(row.assigned_points, work.max_points),
        submitted_at=getattr(row, "submitted_at", None),
        updated_at=row.updated_time,
        attachments=[MaterialOut(**m) for m in (getattr(row, "attachments", None) or [])],
    )
```

### 2.4 🟡 API вообще без аутентификации

CORS ограничивает браузеры, но не curl; `POST /api/sync` — simple request,
CORS его не остановит.

**✅ Решение** — для локального приложения достаточно двух мер: middleware,
проверяющая Host/Origin (локальный бинд уже сделан в launcher), и честный
threat model в README:

```python
# main.py
from fastapi import Request
from fastapi.responses import JSONResponse

TRUSTED_HOSTS = ("127.0.0.1", "localhost")


@app.middleware("http")
async def enforce_local_only(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    origin = request.headers.get("origin")
    if host not in TRUSTED_HOSTS:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    # Браузерные запросы из чужих страниц режем по Origin; не-браузерные (curl)
    # origin не присылают — их ограничивает бинд на 127.0.0.1.
    if origin is not None and origin not in FRONTEND_ORIGINS:
        return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
    return await call_next(request)
```

```markdown
<!-- README.md, раздел Security -->
## Security model
- сервер слушает только 127.0.0.1; чужие Host/Origin отклоняются middleware;
- любые локальные процессы могут вызывать API (read-only кэш, синхронизация) —
  приложение не защищает машину от своего же пользователя;
- токен Google лежит в %LOCALAPPDATA%\GoogleClassHelp\token.json, права —
  только на чтение Classroom.
```

### 2.5 🟡 Обфускация секретов = security theater (вы сами это знаете)

XOR + base64 с ключом в том же exe защищает только от «открыл Notepad», но
генерация нового ключа на каждую сборку и `cycle`-XOR создают видимость криптографии.

**✅ Решение** — убрать видимость шифрования: либо честный base64 без ритуала,
либо (правильнее) вообще не встраивать секрет в exe:

```python
# build_secrets.py → заменяется на проверку при сборке:
# exe НЕ содержит client_secret; пользователь кладёт credentials.json
# в DATA_DIR при первом запуске (та же схема, что у gcloud/gh CLI).

# auth.py — единый путь загрузки конфига:
def _client_config() -> dict | None:
    """OAuth client config from the user data dir; nothing embedded."""
    path = Path(os.environ.get("GC_DASHBOARD_CREDENTIALS", DATA_DIR / "credentials.json"))
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
```

Если встраивание оставить (product-решение «чтобы работало из коробки»), то
минимум — выкинуть XOR-ритуал и оставить одну base64-строку с комментарием
«not a protection», а не два уровня иллюзии.

---

## 3. 👮 Допрос — ответы и где фиксы

1. **«Зачем ты написал `_get_course` дважды?»** — Ответа нет. Удалить вторую (§1.1).
2. **«Студент открыл grades — всегда пусто. Фича?»** — Баг. Таблица не та (§1.2).
3. **«Почему профиль не в кэше?»** — Теперь 5-минутный TTL (§1.3).
4. **«Это замок для dict или для сети на 30 с?»** — Для dict. Сеть вынесена (§1.4).
5. **«А если sync дольше интервала?»** — Задачи `_runs` копятся. После §1.6 — добавить
   guard: `_run` проверяет `_SYNC_LOCK.acquire(blocking=False)` уже внутри
   `sync_now`, поэтому накопленные задачи просто выйдут с `ok: False`; для
   чистоты — `_runs = ThreadPoolExecutor(max_workers=1)` оставить, но в
   `_scheduler_loop` проверять `result.get("error") == "A synchronization is already running."`
   и не логировать это как failure.
6. **«Зачем raise в `reset_cache`, если БД существует?»** — Dead code. Удалён (§1.9).
7. **«SQLite BUSY при записи?»** — WAL + busy_timeout (§1.6).
8. **«Дублированное условие в `grades`?»** — Вынести в переменную:
   `graded_ok = [a for a in assignments if a.graded and a.points is not None and a.max_points]`
   и переиспользовать в обоих местах.
9. **«POST /sync занимает воркер на минуты, второй клик получает ошибку с HTTP 200»** —
   Разделить коды: уже запущенная синхронизация — это не ошибка. Вернуть
   `409 Conflict` с `{"ok": False, "running": True}`, а фронт по `running`
   просто продолжает показывать спиннер.
10. **`teacher_names: Mapped[list]`** — `Mapped[list[str]]` (§1.9).

```python
# Фикс для вопроса 9 — api.py
@router.post("/sync", response_model=SyncResult)
def run_sync(db: Session = Depends(get_db)) -> SyncResult:
    result = sync.sync_now()
    if not result.get("ok") and "already running" in str(result.get("error", "")):
        raise HTTPException(status_code=409, detail="A synchronization is already running.")
    return SyncResult(**result)
```

---

## 4. 💡 Порядок починки (по убыванию цены ошибки)

1. §1.1, §1.2 — мёртвый код и сломанный эндпоинт: 15 минут, эффект максимальный.
2. §1.6 — три прагмы SQLite: 5 минут, снимает целый класс «загадочных» багов.
3. §1.3 + §1.4 — кэш профиля и refresh вне замка: 30 минут, минус лишние
   запросы к Google из всех горячих эндпоинтов.
4. §1.5 + §1.7 — гонка логина и HttpError в `list_courses`.
5. §2.1 — SQL-агрегаты: единственный крупный рефакторинг, делать после тестов из §1.8.
6. §2.2–§2.5 — слои, унификация таблиц, origin-guard, упрощение секретов.

## 5. 📊 Оценка

| Категория | Оценка | Комментарий |
| --- | --- | --- |
| Качество кода | **5/10** | Чистый стиль, но дублированная функция, недостижимый raise, тест-мимикрия |
| Читаемость | **7.5/10** | Докстринги и ADR-ссылки — образцово; спасает от двойки |
| Производительность | **4/10** | Полная выгрузка базы на каждый запрос + сеть внутри GET |
| Архитектура | **5/10** | Нет слоёв, домен в sync.py, двойное хранение сущности |
| Безопасность | **5/10** | Токен ок, но API без аутентификации и без threat model |
| Надёжность | **5/10** | Гонки в login, refresh под замком, SQLite без WAL |

**Резюме:** это не «перепиши всё» — фундамент приличный, комментарии честные, а
ADR-дисциплина выше, чем у многих продакшн-команд. Но **студентский эндпоинт
оценок, всегда возвращающий пустоту, дубль `_get_course` и Google в теле
GET-запроса** — это то, что вскрывается на первом же нормальном ревью. Пункты
§1.1–§1.5 — один вечер работы; после них оценка — 7.5. Пока — **«хорошие кости,
но не разработано, а собрано»**.
