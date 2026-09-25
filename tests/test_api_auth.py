# pyright: reportMissingImports=false
# Backend modules are put on sys.path at runtime by tests/conftest.py; the type
# checker does not execute that, so the flat imports resolve only at runtime.
"""Auth boundary and local-only guard tests."""

import sync


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_status_is_unauthenticated_without_token(client):
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is False
    # §26: identity lives in `user` alone; the flat mirrors are gone.
    assert body["user"] is None


def test_foreign_host_is_forbidden(client):
    # DNS rebinding: a foreign Host must never reach the API (§2.4).
    response = client.get("/api/health", headers={"host": "evil.example"})
    assert response.status_code == 403


def test_foreign_origin_is_forbidden(client):
    response = client.get("/api/health", headers={"origin": "http://evil.example"})
    assert response.status_code == 403


def test_same_origin_post_is_allowed(client, monkeypatch):
    # Production frontend and API share one origin (§27): the origin guard
    # must not block the dashboard's own POSTs, whatever host it runs on.
    monkeypatch.setattr(
        sync, "sync_now", lambda user=None, **kwargs: {"ok": True, "courses": 0}
    )
    response = client.post("/api/sync", headers={"origin": "http://127.0.0.1"})
    assert response.status_code == 200


def test_second_sync_returns_409(client, db):
    # A sync that is already running is a conflict, not a server error (§3.9).
    # Desktop runs inline: hold this owner's per-user lock so sync_now
    # reports ALREADY_RUNNING and the endpoint maps it to 409.
    import ownership
    import sync_service

    owner = ownership.ensure_local_owner(db)
    db.commit()
    lock = sync_service._sync_lock_for(owner.id)
    lock.acquire()
    try:
        response = client.post("/api/sync")
    finally:
        lock.release()
    assert response.status_code == 409
