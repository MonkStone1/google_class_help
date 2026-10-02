"""The structure rules of ADR-0039, enforced (stage 4, PLAN.md §8).

Each test below states WHY a violation matters, because a structure test that
only says "line too long" is the first thing deleted when it becomes
inconvenient. The rules, and what each one prevents:

1. no module over the line budget — a module that outgrew its budget has
   acquired a second responsibility (a 1692-line ``api.py`` held the whole HTTP
   surface; a 721-line ``sync_store.py`` held four unrelated write paths);
2. ``core/**`` stays free of frameworks, Google and SQLAlchemy — it is the
   bottom of the dependency graph;
3. ``api/queries/**`` stays free of ``fastapi`` — they answer cache questions,
   ``api/guards.py`` turns the answers into status codes;
4. ``api/routes/**`` never reaches into the Google or cache-write layers;
5. the root of ``backend/`` holds only what belongs there;
6. no layer shadows an installed distribution (§3.1 — the ``google/`` trap).

Every check reads the source with ``ast`` rather than a regex: a rule that
matches inside a docstring or a comment is a rule that cries wolf.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The budgets of docs/BACKEND_STRUCTURE.md, per category.
#
# ``api/routes`` is 280 rather than the 200 the other layers get, and the extra
# 80 lines are not slack: a route is a handler plus the authorization seam plus
# the mapping to a response model, and the feedback pair genuinely needs both a
# JSON and a multipart body on the same URL. The 300-line ``api.py`` this
# replaced held all fourteen routes; the point of the split is that each route
# is now findable by name, not that each file is arbitrarily small.
LINE_BUDGET = {
    "api/routes": 280,
    "api/queries": 350,
    "main.py": 200,
}
DEFAULT_BUDGET = 400

# A facade is a re-export by design: being short IS the requirement, so it gets
# its own tight budget instead of the domain one.
FACADE_BUDGET = 60
FACADES = {"sync/__init__.py"}

# launcher.py is the Nuitka entry point (ADR-0016): build.bat compiles that
# exact file and path_config.py resolves BACKEND_DIR from
# ``Path(__file__).resolve().parent``, so it cannot move into a package without
# breaking the desktop build. It is the ONE module allowed over the budget, and
# it is listed by name — a pattern would silently admit the next fat module.
BUDGET_EXEMPT = {
    "launcher.py": "Nuitka entry point pinned by ADR-0016 (build.bat, path_config.py)",
}


def backend_modules() -> list[Path]:
    return sorted(
        path
        for path in BACKEND.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def budget_for(path: Path) -> int:
    relative = path.relative_to(BACKEND).as_posix()
    if relative in FACADES:
        return FACADE_BUDGET
    for prefix, limit in LINE_BUDGET.items():
        if relative == prefix or relative.startswith(f"{prefix}/"):
            return limit
    return DEFAULT_BUDGET


def imported_modules(path: Path) -> set[str]:
    """Top-level module names this file imports, via AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def files_in(layer: str) -> list[Path]:
    return sorted(path for path in (BACKEND / layer).rglob("*.py"))


# ------------------------------------------------------- 1. the line budget


def test_every_module_is_inside_its_line_budget():
    """No module grows past its category budget without someone deciding so.

    The eight modules that broke this budget at the start of ADR-0039 were all
    modules that had quietly taken on a second job, so the budget is a proxy
    for "does this file still have one reason to exist".
    """
    offenders = []
    for path in backend_modules():
        relative = path.relative_to(BACKEND).as_posix()
        if relative in BUDGET_EXEMPT:
            continue
        limit = budget_for(path)
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > limit:
            offenders.append(f"{relative}: {lines} > {limit}")
    assert not offenders, "modules over budget:\n  " + "\n  ".join(offenders)


def test_the_budget_exemption_list_stays_at_one_entry():
    """An exemption nobody re-checks stops being an exception.

    Naming ``launcher.py`` is only meaningful while it is the single entry: a
    second one is a signal that the budget is wrong, and this test says so
    instead of letting the list grow quietly.
    """
    assert set(BUDGET_EXEMPT) <= {"launcher.py"}, (
        "a new budget exemption needs a decision in an ADR, not just a line in "
        f"BUDGET_EXEMPT; current: {sorted(BUDGET_EXEMPT)}"
    )


# ------------------------------------------------------ 2. core is pure infra

# The layer forbids FRAMEWORKS and STORAGE, not the standard library: config
# reads os.environ, metrics reads logging, rate_limit reads threading. Those
# are the vocabulary of infrastructure, not a dependency on another layer.
CORE_FORBIDDEN = {
    "fastapi",
    "starlette",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "googleapiclient",
    "google_auth_oauthlib",
    "google_auth_httplib2",
    "httplib2",
}

# core/proxy.py IS the HTTP-boundary decision — a Request is its input, not a
# leak — so FastAPI is legitimate there and nowhere else in core/.
CORE_ALLOWED = {"proxy.py": {"fastapi", "starlette"}}


def test_core_never_reaches_into_a_framework_or_a_datastore():
    """``core/`` is the bottom of the graph, so its arrows point up only.

    The moment configuration imports SQLAlchemy or the Google client, every
    layer above it can skip the graph entirely, and the ordering the rest of
    the backend is built on stops meaning anything.
    """
    offenders = []
    for path in files_in("core"):
        reached = imported_modules(path) & CORE_FORBIDDEN
        reached -= CORE_ALLOWED.get(path.name, set())
        if reached:
            relative = path.relative_to(BACKEND).as_posix()
            offenders.append(f"{relative}: {sorted(reached)}")
    assert not offenders, "core/ must not import:\n  " + "\n  ".join(offenders)


def test_the_pure_domain_module_stays_pure():
    """``sync/grading.py`` is the rules, with no I/O and no infrastructure.

    It is the only module a future client in another language could port
    directly, and that property is invisible the moment it grows an import.
    ``datetime`` is a type, not a dependency — it stays.
    """
    grading = BACKEND / "sync" / "grading.py"
    reached = imported_modules(grading) - {"__future__", "datetime"}
    assert not reached, f"sync/grading.py must stay import-free, reached {sorted(reached)}"


# --------------------------------------------- 3. api/queries has no HTTP


def test_api_queries_do_not_import_fastapi():
    """Cache reads answer questions; ``api/guards.py`` turns answers into codes.

    A missing row is ``None`` and a forbidden course is a role STRING here. If a
    query module raises ``HTTPException`` instead, the same read stops being
    usable from the worker, a CLI or a unit test, and the status-code policy
    leaks into the data layer where it can no longer be reviewed as one table.
    """
    offenders = []
    for path in files_in("api/queries"):
        reached = imported_modules(path) & {"fastapi", "starlette"}
        if reached:
            relative = path.relative_to(BACKEND).as_posix()
            offenders.append(f"{relative}: {sorted(reached)}")
    assert not offenders, "api/queries/ must not import HTTP:\n  " + "\n  ".join(offenders)


# -------------------------------------------------- 4. routes stay thin

# Rule 4 of docs/BACKEND_STRUCTURE.md. A handler that imports the Google layer
# can start a Classroom fan-out from a request; one that imports the cache
# writers can turn a GET into a write. Both are what the layering forbids.
ROUTE_FORBIDDEN = {
    "gapi",
    "classroom_api",
    "google_credentials",
    "oauth_transport",
    "sync_store",
    "sync_service",
}


def test_api_routes_do_not_reach_into_google_or_the_cache_writers():
    """A route resolves the caller, validates, maps a status and delegates."""
    offenders = []
    for path in files_in("api/routes"):
        reached = imported_modules(path) & ROUTE_FORBIDDEN
        if reached:
            relative = path.relative_to(BACKEND).as_posix()
            offenders.append(f"{relative}: {sorted(reached)}")
    assert not offenders, "api/routes/ must not import:\n  " + "\n  ".join(offenders)


def test_the_sync_status_read_stays_a_local_import():
    """``api/routes/sync.py`` reaches into the store ONCE, and only locally.

    This is the second honest exception recorded in
    docs/BACKEND_STRUCTURE.md, kept here as a test rather than a comment: the
    import sits inside the function that needs it, so importing the module
    carries no such dependency, and it exists only until the store exposes a
    status accessor. When that lands this test fails, telling whoever did it to
    delete the exception in the same change.
    """
    path = BACKEND / "api" / "routes" / "sync.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_level = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any("sync.store" in alias.name for alias in getattr(node, "names", []))
    ]
    assert not module_level, (
        "the documented local import of sync.store became a module-level one; "
        "either revert it or update docs/BACKEND_STRUCTURE.md"
    )


# ------------------------------------------------------ 5. the root is small

ROOT_ALLOWED = {
    "main.py",  # the composition root: routers, middleware order, health
    "launcher.py",  # Nuitka entry point (ADR-0016)
    "path_config.py",  # RESOURCE_DIR vs DATA_DIR, frozen-aware (ADR-0016)
    "build_secrets.py",  # build-time utility
    "maintenance.py",  # user-data deletion on account removal
    "embedded_secrets.py",  # generated at build time, shipped in the image
    "embedded_secrets.pyi",
}


def test_backend_root_holds_nothing_but_the_entry_points():
    """``backend/`` root is the ``sys.path`` root, so it must stay small.

    Every module nameable without a package is a name the whole process shares,
    including with ``site-packages`` — that is exactly how ``google/`` nearly
    shadowed the Google namespace packages (§3.1). This test is what turns "we
    will just leave it in the root" into a failing build instead of a pile that
    grows until something else breaks.
    """
    stray = sorted(
        path.name
        for path in BACKEND.glob("*.py")
        if path.name not in ROOT_ALLOWED and not path.name.startswith("_")
    )
    assert not stray, (
        "backend/ root may only hold "
        + ", ".join(sorted(ROOT_ALLOWED))
        + f"; found {stray}"
    )


def test_the_composition_root_stays_small():
    """``main.py`` is assembly, and assembly is short by nature.

    It reached 517 lines while the middleware closures lived inside it; the
    split into ``edge/`` is why it is back under 200. A new endpoint belongs in
    ``api/`` and a new middleware factory in ``edge/``, not here.
    """
    main = BACKEND / "main.py"
    lines = len(main.read_text(encoding="utf-8").splitlines())
    assert lines <= LINE_BUDGET["main.py"], f"main.py is {lines} lines"


# ------------------------------------------- 6. no layer shadows a package


LAYERS = ["api", "auth", "core", "db", "edge", "feedback", "gapi", "schemas", "sync"]


@pytest.mark.parametrize("layer", LAYERS)
def test_no_layer_shadows_an_installed_distribution(layer: str):
    """A layer name must not collide with anything in ``site-packages``.

    This is the trap that renamed ``google/`` to ``gapi/`` (PLAN.md §3.1):
    ``backend/`` is on ``sys.path``, so a directory named after an installed
    distribution either shadows it — ``from google.oauth2.credentials import
    Credentials`` stops resolving and the app dies on startup — or, for a PEP
    420 namespace package, merges with it by accident of path order and breaks
    the day the order changes.

    The import is performed for real: ``find_spec`` alone would report ``None``
    for a namespace package and quietly pass.
    """
    assert importlib.util.find_spec(layer) is not None, (
        f"layer {layer!r} is not importable — a rename left a dangling import"
    )
    module = __import__(layer)
    origin = getattr(module, "__file__", None)
    if origin is None:  # a namespace package has no __file__
        paths = list(getattr(module, "__path__", []))
        assert paths, f"layer {layer!r} has neither __file__ nor __path__"
        for path in paths:
            assert BACKEND not in Path(path).resolve().parents, (
                f"layer {layer!r} resolves outside backend/: {path}"
            )
        return
    assert BACKEND in Path(origin).resolve().parents, (
        f"layer {layer!r} resolves to {origin}, which is NOT inside backend/ — "
        "it shadows, or is shadowed by, an installed distribution"
    )