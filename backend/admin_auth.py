"""Administrator authorization (ADR-0035).

One dependency, used by every admin endpoint: the caller, if their address is
in the ``ADMIN_EMAILS`` allow-list; 403 otherwise. There is no role column, no
"first user is admin", no wildcard and no hardcoded address — the list lives in
the process environment (config.ADMIN_EMAILS) and is read fail-closed (empty or
missing ⇒ nobody is an administrator).

Deliberately thin:

- it does NOT parse the session. ``get_current_user`` has already rejected an
  anonymous request with 401 (and the session gate does it even earlier), so
  re-implementing session resolution here would create a second way to learn who
  the caller is — exactly what §22 forbids;
- it does NOT return the address list. The frontend learns a single boolean
  (``UserOut.is_admin``) computed by the same membership test
  (``config.is_admin_email``), so the allow-list itself never reaches a browser
  bundle, a log line or the OpenAPI document.

An empty address — the desktop local owner has ``email is None`` — is never an
administrator: the desktop build therefore cannot reach the admin surface.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets
#       (same dispensation as api.py / ownership.py).

from fastapi import Depends, HTTPException

import ownership
from config import is_admin_email
from models_auth import User


def require_admin(
    user: User = Depends(ownership.get_current_user),
) -> User:
    """The caller, if a configured administrator; 403 otherwise.

    401 is deliberately absent: an unauthenticated request never reaches here —
    the hosted session gate and ``ownership.get_current_user`` answer it first.
    """
    if not is_admin_email(user.email):
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user
