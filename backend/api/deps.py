"""Dependencies shared by the API routers (ADR-0039).

Kept in one module so every route resolves "who is calling" the same way —
a router that reached for the user id itself is the exact defect §12/§13
(user isolation) exists to prevent.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.

from fastapi import Depends

import ownership
from models_auth import User

# ------------------------------------------------------- current user (§13)


def current_user_id(user: User = Depends(ownership.get_current_user)) -> int:
    """The authenticated user's id — the cache owner of this request (§13).

    Thin derivation over ``ownership.get_current_user``, which validates
    the hosted session (or resolves the desktop local owner) itself and
    never trusts a request-supplied id. Most cache reads need only the id;
    the endpoints that need the profile take the user dependency directly.
    """
    return user.id