"""Generate the server-side secrets for the hosted deployment (stage 2, §9).

The hosted service needs exactly one generated secret today:

- GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY — the Fernet key encrypting the
  Google OAuth tokens stored in ``oauth_tokens`` (token_crypto.py).

Application sessions use opaque random tokens stored hashed in the
database, so no static session-signing secret is required by this design
(decided in ADR-0020).

Usage (from the project root):

    .venv\\Scripts\\python.exe tools\\generate_hosted_secrets.py

The values are printed to stdout ONLY. Never write them into a file inside
the repository: put them into the hosting platform's secret store (or a
local ``.env`` that is git-ignored).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core.crypto import KEY_ENV_VAR, generate_key  # import after sys.path

print(f"{KEY_ENV_VAR}={generate_key()}")
