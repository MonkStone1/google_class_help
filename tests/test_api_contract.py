"""Snapshot of the public HTTP contract (ADR-0039, restructure Phase 0).

The backend used to serve every ``/api`` endpoint from one 1692-line
``backend/api.py``. Splitting it into a package of routers must not move,
rename or re-order a single endpoint: the frontend's types are generated from
``frontend/openapi.json`` (``npm run gen:api:file``), so an endpoint that
quietly disappears — or whose handler gets renamed, which changes its
``operationId`` — breaks ``tsc``, or worse, ships.

This module pins both halves of that promise:

- the exact set of ``(path, method, operationId)`` the app answers, for the
  desktop app and for the hosted one;
- every ``/api`` handler served by the main router lives under ``api.routes.*``,
  so the HTTP surface can never grow a hidden endpoint inside ``main.py`` or in
  a domain module again.

The snapshot is read from ``app.openapi()``, not ``app.routes``: the installed
FastAPI wraps ``include_router`` in an ``_IncludedRouter`` object, so
``app.routes`` holds wrappers rather than flat ``APIRoute`` entries. The
OpenAPI document is the contract the frontend actually consumes, so it is also
the more precise source.

To change the API on purpose: update the snapshot here AND regenerate
``frontend/openapi.json``. A test failing after a move is a bug in the move,
not a test to relax.
"""

from fastapi import APIRouter
from fastapi.routing import APIRoute

from main import app, create_app

# ``path|method|operationId``, one endpoint per line. Compact text so a
# reviewer can diff the whole surface in one glance instead of reading tuples.
_DESKTOP_CONTRACT = """
/api/admin/admins|GET|list_admins_api_admin_admins_get
/api/admin/admins|POST|create_admin_api_admin_admins_post
/api/admin/admins/|GET|list_admins_api_admin_admins__get
/api/admin/admins/|POST|create_admin_api_admin_admins__post
/api/admin/admins/{admin_id}|DELETE|delete_admin_api_admin_admins__admin_id__delete
/api/admin/feedback/stats|GET|feedback_stats_api_admin_feedback_stats_get
/api/admin/feedback/tickets|GET|list_tickets_api_admin_feedback_tickets_get
/api/admin/feedback/tickets/{ticket_id}|GET|read_ticket_api_admin_feedback_tickets__ticket_id__get
/api/admin/feedback/tickets/{ticket_id}|PATCH|set_status_api_admin_feedback_tickets__ticket_id__patch
/api/admin/feedback/tickets/{ticket_id}|DELETE|delete_ticket_api_admin_feedback_tickets__ticket_id__delete
/api/admin/feedback/tickets/{ticket_id}/messages|POST|reply_to_ticket_api_admin_feedback_tickets__ticket_id__messages_post
/api/assignments|GET|list_assignments_api_assignments_get
/api/assignments/overdue|GET|overdue_api_assignments_overdue_get
/api/assignments/upcoming|GET|upcoming_api_assignments_upcoming_get
/api/auth/login|POST|login_api_auth_login_post
/api/auth/logout|POST|logout_api_auth_logout_post
/api/auth/status|GET|auth_status_api_auth_status_get
/api/cache|DELETE|clear_cache_api_cache_delete
/api/calendar|GET|calendar_api_calendar_get
/api/courses|GET|list_courses_api_courses_get
/api/courses/{course_id}|GET|course_detail_api_courses__course_id__get
/api/courses/{course_id}/coursework|GET|course_coursework_api_courses__course_id__coursework_get
/api/courses/{course_id}/coursework/{coursework_id}|GET|coursework_detail_api_courses__course_id__coursework__coursework_id__get
/api/courses/{course_id}/coursework/{coursework_id}/submissions|GET|coursework_submissions_api_courses__course_id__coursework__coursework_id__submissions_get
/api/courses/{course_id}/grades|GET|course_grades_api_courses__course_id__grades_get
/api/courses/{course_id}/students|GET|course_students_api_courses__course_id__students_get
/api/courses/{course_id}/students/{student_id}/grades|GET|student_grades_api_courses__course_id__students__student_id__grades_get
/api/feedback/attachments/{attachment_id}|GET|download_attachment_api_feedback_attachments__attachment_id__get
/api/feedback/tickets|GET|list_my_tickets_api_feedback_tickets_get
/api/feedback/tickets|POST|create_ticket_api_feedback_tickets_post
/api/feedback/tickets/{ticket_id}|GET|get_my_ticket_api_feedback_tickets__ticket_id__get
/api/feedback/tickets/{ticket_id}/messages|POST|reply_to_ticket_api_feedback_tickets__ticket_id__messages_post
/api/grades|GET|grades_api_grades_get
/api/health|GET|health_api_health_get
/api/me|GET|me_api_me_get
/api/me|DELETE|delete_own_account_api_me_delete
/api/me/cache|DELETE|clear_own_cache_api_me_cache_delete
/api/me/google|DELETE|disconnect_google_account_api_me_google_delete
/api/ready|GET|ready_api_ready_get
/api/status|GET|status_api_status_get
/api/sync|POST|run_sync_api_sync_post
"""

# Endpoints only the HOSTED app adds. Its OAuth router is included BEFORE the
# main router so these shadow the desktop ``/api/auth/*`` handlers; the hosted
# set therefore also contains every desktop operation, which is why this file
# records the delta instead of a second full snapshot.
_HOSTED_ONLY_CONTRACT = """
/api/auth/callback|GET|callback_api_auth_callback_get
/api/auth/login|GET|login_api_auth_login_get
/api/auth/login/start|POST|login_start_api_auth_login_start_post
/api/auth/turnstile|GET|turnstile_config_api_auth_turnstile_get
"""
def _parse(contract: str) -> set[tuple[str, str, str]]:
    return {
        tuple(line.split("|"))  # type: ignore[misc]
        for line in contract.split()
        if line
    }


EXPECTED_OPERATIONS = _parse(_DESKTOP_CONTRACT)
EXPECTED_HOSTED_ONLY = _parse(_HOSTED_ONLY_CONTRACT)


def operations(application) -> set[tuple[str, str, str]]:
    """``(path, method, operationId)`` of every documented endpoint."""
    return {
        (path, method.upper(), operation.get("operationId"))
        for path, methods in application.openapi()["paths"].items()
        for method, operation in methods.items()
        if method != "parameters"
    }


def iter_routes(router):
    """Yield every ``APIRoute`` under ``router``, unpacking included routers.

    FastAPI's lazy ``include_router`` stores an ``_IncludedRouter`` wrapper
    instead of copying routes into the parent, so iterating ``router.routes``
    directly stops at the wrapper and sees nothing at all.
    """
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute):
            yield route
            continue
        nested = getattr(route, "original_router", None) or getattr(
            route, "router", None
        )
        if nested is not None:
            yield from iter_routes(nested)
        elif hasattr(route, "routes"):
            yield from iter_routes(route)


def test_the_desktop_api_surface_is_unchanged():
    assert operations(app) == EXPECTED_OPERATIONS


def test_the_hosted_api_adds_only_the_oauth_endpoints():
    assert operations(create_app(hosted=True)) - operations(app) == EXPECTED_HOSTED_ONLY


def test_every_api_handler_lives_in_a_router_module():
    """No endpoint may hide in ``main.py``, in a domain module or in a closure."""
    from api import router as api_router

    modules = {
        route.endpoint.__module__
        for route in iter_routes(api_router)
        if route.endpoint.__module__.startswith("api.")
    }
    unexpected = {
        module
        for module in modules
        if module != "api" and not module.startswith("api.routes.")
    }
    assert not unexpected, (
        "handlers outside api/routes/: " + ", ".join(sorted(unexpected))
    )
    # Sanity: the walk really reaches the handlers instead of seeing nothing.
    assert len(modules) > 1


def test_the_router_keeps_its_api_prefix():
    """``main.py`` mounts ``api.router`` unchanged — keep it that way."""
    from api import router as api_router

    assert isinstance(api_router, APIRouter)
    assert api_router.prefix == "/api"