"""The administrator management API — Super Admin only (ADR-0036).

Every handler takes ``admin: User = Depends(require_super_admin)``, so a plain
administrator cannot list, add or remove administrators by any means, including
by forging a request body: the guard reads the validated session only, and the
endpoints below never accept an identity claim from the caller.

The status codes are part of the contract, not an afterthought:

- **403** — authenticated, but not the Super Admin (a plain administrator lands
  here too: they may answer tickets, but they may not manage the registry);
- **409** — a conflict with the configuration or with an existing row: a
  duplicate address, or an attempt to add/remove the Super Admin themselves;
- **422** — the address is malformed (raised by ``schemas_admins``);
- **404** — the row to delete does not exist.

None of this echoes a stack trace or a Pydantic error object: the project
answers with short ``detail`` strings, and the ``SUPER_ADMIN_EMAIL`` value is
never logged or returned.
"""

# ruff: noqa: B008
# B008: FastAPI's documented dependency-injection idiom uses Depends() in an
#       argument default (same dispensation as api.py).

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config
from admin_auth import display_name_from_email, require_super_admin
from config import normalize_email
from database import get_db
from models_admin import Admin
from models_auth import User
from schemas_admins import AdminCreateIn, AdminOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/admins", tags=["admin"])


def _admin_out(row: Admin) -> AdminOut:
    """One registry row, with the display name derived from its address."""
    return AdminOut(
        id=row.id,
        email=row.email,
        name=display_name_from_email(row.email),
        created_at=row.created_at,
    )


@router.get("", response_model=list[AdminOut])
@router.get("/", response_model=list[AdminOut])
def list_admins(
    admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> list[AdminOut]:
    """Every normal administrator, newest first.

    The Super Admin is absent by construction (their identity lives only in
    ``SUPER_ADMIN_EMAIL``), so the list can never contain the one account that
    manages it. ``admin`` is the guard's return value, not an input.

    Registered under BOTH ``""`` and ``"/"`` on purpose: with only ``"/"`` the
    un-slashed ``/api/admin/admins`` matches no route, misses the 403 below and
    falls through to the SPA fallback — which answers an unauthorized probe with
    200 and an HTML shell instead of the contract's 403.
    """
    rows = db.scalars(select(Admin).order_by(Admin.id.desc())).all()
    return [_admin_out(row) for row in rows]


@router.post("", response_model=AdminOut, status_code=201)
@router.post("/", response_model=AdminOut, status_code=201)
def create_admin(
    payload: AdminCreateIn,
    admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> AdminOut:
    """Add one administrator by e-mail; 409 on a duplicate or on the Super Admin.

    ``payload.email`` is already normalized by the model's validator, so the
    duplicate comparison and the stored value are the same spelling.

    The duplicate is checked twice on purpose: the SELECT answers the normal
    case with a clean 409, and the unique index answers the race (two requests
    passing the SELECT at the same moment) that a SELECT alone cannot. Failures
    never widen access — both paths refuse.
    """
    normalized = normalize_email(payload.email)
    if config.SUPER_ADMIN_EMAIL and normalized == config.SUPER_ADMIN_EMAIL:
        # Storing the Super Admin as a row would create a second source of truth
        # for a role the environment already owns, and a way to delete them.
        raise HTTPException(
            status_code=409,
            detail="This account is already the super administrator.",
        )
    existing = db.execute(
        select(Admin.id).where(Admin.email == normalized)
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="This account is already an administrator."
        )

    row = Admin(
        email=normalized,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        # The unique index fired: another request inserted the same address
        # between our SELECT and this INSERT.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This account is already an administrator."
        ) from exc
    db.refresh(row)
    # The row ID is logged, never the Super Admin address and never the value of
    # SUPER_ADMIN_EMAIL: an audit line must not become a credential store.
    logger.info("Administrator id=%s added by user id=%s.", row.id, admin.id)
    return _admin_out(row)


@router.delete("/{admin_id}", status_code=204)
def delete_admin(
    admin_id: int,
    admin: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Remove one administrator; 404 when the row is gone, 409 for the Super Admin.

    The 409 branch is reachable only if ``SUPER_ADMIN_EMAIL`` was changed AFTER
    the row was inserted — the POST endpoint refuses to create such a row in the
    first place. It is kept because deleting the one account that manages the
    registry would be unrecoverable through the UI.
    """
    row = db.get(Admin, admin_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Administrator not found.")
    if config.SUPER_ADMIN_EMAIL and normalize_email(row.email) == config.SUPER_ADMIN_EMAIL:
        raise HTTPException(
            status_code=409,
            detail="The super administrator cannot be removed here.",
        )
    db.delete(row)
    db.commit()
    logger.info("Administrator id=%s removed by user id=%s.", admin_id, admin.id)
    return Response(status_code=204)