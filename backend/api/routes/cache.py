"""Cache-clearing endpoints.

Two paths with identical behaviour, kept side by side: the older ``/cache`` and
the explicit ``/me/cache`` (stage 9, §66) that says what the code already does —
delete the CALLER's cache, never anyone else's. Existing desktop clients use
the first, new ones should use the second.

Both are rate-limited per IP in middleware (``main.py``, ``§39``), not here.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default; it is not the mutable-default bug the rule targets.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import sync
from api.deps import current_user_id
from db.session import get_db

router = APIRouter()


@router.delete("/cache")
def clear_cache(
    confirm: bool = Query(default=False),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to clear all locally cached data.",
        )
    # Deletes only the calling user's cache rows (stage 3; audit P4/Y4).
    sync.reset_cache(db, owner_id)
    return {"ok": True, "cleared": True}


@router.delete("/me/cache")
def clear_own_cache(
    confirm: bool = Query(default=False),
    owner_id: int = Depends(current_user_id),
    db: Session = Depends(get_db),
) -> dict:
    """Explicit alias of ``DELETE /api/cache`` (stage 9, §66).

    Same handler shape, same per-user scope, same ``confirm=true`` gate —
    the path only says what the code already does: delete the CALLER's
    cache, never anyone else's. Kept side by side with ``/api/cache`` so
    existing desktop clients keep working while new clients can use the
    unambiguous name.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=true to clear all locally cached data.",
        )
    sync.reset_cache(db, owner_id)
    return {"ok": True, "cleared": True}