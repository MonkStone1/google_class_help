# Google Class Help — hosted container image (migration stage 10, §54/§72).
#
# Two stages: the frontend bundle is built with Node, then copied into a slim
# Python runtime that installs ONLY backend/requirements-prod.txt. The image
# never contains .env, credentials.json, embedded_secrets.py, data/ or any
# database file (.dockerignore enforces that at the build-context level).
#
# One image serves both roles:
#   web    → uvicorn main:app   (from /app/backend)
#   worker → python sync_worker.py (same image, different command)

# --------------------------------------------------------------- frontend
FROM node:22-slim AS frontend-build

WORKDIR /build/frontend
# `npm ci` needs the lockfile; copy only the manifests first for layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl is used by the container healthcheck (/api/ready); tini gives the
# worker a real init so SIGTERM from `docker stop` reaches Python.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root application user (§22).
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

# Pinned runtime dependencies only — no dev/test packages in the image (§73).
COPY backend/requirements-prod.txt /app/backend/requirements-prod.txt
RUN pip install -r /app/backend/requirements-prod.txt

# Application code, migrations and the built frontend.
COPY backend/ /app/backend/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

# Hosted data directory (tokens live in PostgreSQL; this is only for any
# non-database files the service may need) — mounted as a volume in compose.
RUN mkdir -p /data && chown -R app:app /app /data

USER app

WORKDIR /app/backend

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
# Deliberately NO --proxy-headers: uvicorn must not rewrite request.client
# before backend/proxy.py applies the GC_DASHBOARD_TRUSTED_PROXIES rule (§29).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
