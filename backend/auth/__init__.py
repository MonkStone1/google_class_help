"""Authentication, identity and roles (ADR-0039).

One package for the two things that answer "who is calling, and what may they
do", because they were one question split across four flat modules and the
import cycle between them (``identity`` → ``ownership`` → ``hosted`` →
``identity``) is the reason ``auth/hosted.py`` still resolves ``_user_out``
lazily.

- ``identity``  — the profile cache and the ``UserOut``/``AuthStatus``
  projection. ONE resolver, shared by the desktop ``/auth/status`` and the
  hosted one, so the role flags the UI reads can never disagree with the verdict
  the API enforces (ADR-0036).
- ``ownership`` — "whose rows may this request touch": the session user in
  hosted mode, the desktop local owner otherwise (§12/§13).
- ``roles``     — the administrator registry and the Super-Admin check.
- ``desktop``   — the loopback OAuth flow of the desktop build (ADR-0019). Never
  imported on the hosted startup path (§32).
- ``hosted``    — web OAuth, sessions and the ``/api/auth/*`` router (ADR-0020).

Budget: ≤ 400 lines per module. ``hosted.py`` is at the limit and is the next
split (``session``/``oauth_flow``/``routes``).
"""
