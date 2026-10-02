"""The single place that talks to Google (ADR-0039).

Deliberately NOT named ``google/``: ``backend/`` is on ``sys.path``, so a
top-level ``google`` package would shadow the namespace package that
``google-auth``, ``google-api-python-client`` and ``google-auth-httplib2``
install into ``site-packages/google`` — and ``from google.oauth2.credentials
import Credentials`` (needed by ``auth/desktop.py``, this package's credentials
module and the OAuth transport) would stop resolving. PEP 420 namespace
packages merge only by accident of ``sys.path`` order, so the layer is called
``gapi/``. ``tests/test_backend_structure.py`` pins that decision with
``test_no_layer_shadows_an_installed_package``.

- ``classroom``       — the discovery client, pagination, retries, request stats.
- ``credentials``     — the user-scoped credential layer (§15).
- ``oauth_transport`` — scopes, code exchange and refresh (§2/§40).
- ``dates``           — parsing of the Classroom date shapes.

Nothing above this layer imports ``googleapiclient``/``google_auth_*``; the rest
of the backend reaches Google only through these modules (ADR-0001).

Budget: ≤ 400 lines per module.
"""

# Imported individually by consumers; nothing is re-exported here so that
# importing the package cannot drag in httplib2 or the credential layer.
