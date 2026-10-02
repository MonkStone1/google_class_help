"""Identity projection of the caller (ADR-0039, Phase 1 of the backend split).

The per-user profile cache and the ``UserOut``/``AuthStatus`` builders lived
inside the 1692-line ``api.py``. They are not HTTP routing: ``hosted_auth.py``
builds its own ``/auth/status`` from the SAME projection, so keeping them in a
router module would either duplicate the role flags (ADR-0036 promises one
resolver) or drag a router import into the hosted auth path.

``api/routes/auth.py`` and ``hosted_auth.py`` therefore both call THIS module —
never a re-export of it. That is deliberate: the tests patch
``api.identity._cached_profile`` / ``api.identity.ClassroomClient``
(``tests/test_user_isolation.py``, ``tests/test_stage9_limits_capacity.py``,
``tests/test_teacher_mode.py``), and a re-export through ``api/__init__.py``
would leave the handlers calling the original.

# ruff: noqa: B008, DTZ005, DTZ901
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.
# DTZ005/DTZ901: the cache stores naive local datetimes on purpose (ADR-0004);
#       due dates arrive from Classroom without a timezone.
"""

import threading
import time

from sqlalchemy.orm import Session

from db.models.accounts import User
from gapi.classroom import ClassroomClient, build_service
from schemas.dashboard import AuthStatus, UserOut

# ------------------------------------------------------- user profile (§17)

# The frontend polls the status endpoints every ~1.5 s while logging in or following a queued/running sync, and
# a network roundtrip to Google inside every poll is unacceptable. The
# profile changes about once a year, so it is cached for five minutes; the
# network call itself runs OUTSIDE the lock.
#
# The cache is keyed by the LOCAL USER ID (§17): one entry per user, never a
# process-global "last profile" another user could read. Hosted users do not
# use it at all — their `users` row is the authoritative profile, refreshed
# from Google at every login (§7) — so this path serves the desktop build's
# single local owner, whose row stays empty until the first Google lookup.
_profile_lock = threading.Lock()
_profile_cache: dict[int, tuple[float, str | None, str | None]] = {}
PROFILE_TTL_SECONDS = 300


def _cached_profile(user: User, creds) -> tuple[str | None, str | None]:
    """Profile of ONE user, cached under that user's id (§17).

    A users row that already carries a profile (hosted: written at login)
    is returned directly; otherwise Google userinfo is asked once and the
    answer is remembered under ``user.id`` for PROFILE_TTL_SECONDS. User B
    can never receive User A's cached name/email: lookups and writes use
    the id, not a module global.
    """
    if user.display_name or user.email:
        return user.display_name, user.email
    with _profile_lock:
        cached = _profile_cache.get(user.id)
        if cached is not None and time.monotonic() - cached[0] < PROFILE_TTL_SECONDS:
            return cached[1], cached[2]
    profile = ClassroomClient(build_service(creds)).get_user_profile()
    name = profile.get("name", {})
    value = (
        name.get("fullName"),
        profile.get("emailAddress") or name.get("fullName"),
    )
    with _profile_lock:
        _profile_cache[user.id] = (time.monotonic(), value[0], value[1])
    return value


def _reset_profile_cache(user_id: int | None = None) -> None:
    """Drop one user's cached profile (§17); no id clears every entry."""
    with _profile_lock:
        if user_id is None:
            _profile_cache.clear()
        else:
            _profile_cache.pop(user_id, None)


def _user_out(user: User, db: Session) -> UserOut:
    """The identity fields of the caller (§24) plus the role flags (ADR-0036).

    Built from the local ``users`` row only — never from a Google credential,
    token or OAuth object, none of which may appear in any response. Both
    ``is_admin`` and ``is_super_admin`` come from the SAME
    ``admin_auth.resolve_role`` call the API guards use, so the flag the UI reads
    can never disagree with the verdict the API enforces.
    """
    from auth.roles import ROLE_SUPER_ADMIN, ROLE_USER, resolve_role

    role = resolve_role(db, user.email)
    return UserOut(
        id=user.id,
        name=user.display_name,
        email=user.email,
        is_admin=role != ROLE_USER,
        is_super_admin=role == ROLE_SUPER_ADMIN,
    )


def _build_auth_status(user: User, db: Session) -> AuthStatus:
    """AuthStatus of ONE user (§16) with their own profile (§17).

    Hosted: the ``users`` row is the authoritative profile (refreshed from
    Google at every login, §7) and there is no loopback login state.
    Desktop: the loopback flow's single-account state, plus the Google
    userinfo profile cached under the local owner's id.

    §24/§26: the payload describes THIS browser's application session,
    carries no OAuth internals (no access/refresh token, no client secret,
    no authorization code), and exposes identity only through ``user``.

    The role flags come from ``_user_out`` (ADR-0036), i.e. from
    ``admin_auth.resolve_role`` — the same resolver the API guards use.
    """
    if user.provider == "google":
        return AuthStatus(
            authenticated=True,
            login_in_progress=False,
            error=None,
            auth_url=None,
            user=_user_out(user, db),
        )
    # Desktop-only branch: auth (the loopback flow) is imported here so the
    # hosted service never loads the desktop module (migration stage 8, §32).
    from auth import desktop

    status = desktop.login_status()
    identity: UserOut | None = None
    if status["authenticated"]:
        creds = desktop.get_valid_credentials()
        if creds is not None:
            user_name, user_email = _cached_profile(user, creds)
            # The desktop local owner has no address of their own (``email is
            # None``), so both role flags are False by construction there — the
            # desktop build cannot reach the admin surface at all. The flags
            # themselves come from the shared resolver, not from a second test.
            from auth.roles import ROLE_SUPER_ADMIN, ROLE_USER, resolve_role

            role = resolve_role(db, user.email or user_email)
            identity = UserOut(
                id=user.id,
                name=user_name,
                email=user_email,
                is_admin=role != ROLE_USER,
                is_super_admin=role == ROLE_SUPER_ADMIN,
            )
    return AuthStatus(**status, user=identity)


def _is_authenticated(user: User) -> bool:
    """Signed-in state alone — no profile lookup (§17/§26).

    ``/api/status`` is polled every ~1.5 s while a sign-in is in flight, so
    it must not reach Google for identity fields it no longer exposes.
    """
    if user.provider == "google":
        return True
    from auth import desktop

    return bool(desktop.login_status().get("authenticated"))