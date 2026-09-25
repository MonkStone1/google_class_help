"""Dump the FastAPI OpenAPI schema for the frontend type generation.

``npm run gen:api`` (in frontend/) pipes a running backend into
openapi-typescript, which produces ``src/api-schema.d.ts``; a Pydantic field
that is renamed or removed then fails ``tsc`` instead of surfacing as a
broken page at runtime. This script does the same without the server: it only
imports the app and serializes its schema, so it can run in an offline
checkout.

Usage (from the project root):

    .venv\\Scripts\\python.exe tools\\dump_openapi.py > frontend\\openapi.json
    cd frontend && npx prettier --write openapi.json && npm run gen:api:file

The raw dump is minified single-line JSON, while the committed
``openapi.json`` is prettier-formatted (``printWidth: 80``) — always run the
prettier pass before committing, or the diff will be unreadable.
"""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from main import app  # import after sys.path: backend/ is not a package

# Windows consoles default to a legacy code page; the schema carries
# non-ASCII docstrings (e.g. "students \u00d7 assignments").
writer = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
json.dump(app.openapi(), writer, ensure_ascii=False)
writer.flush()
