"""The feedback-ticket feature (ADR-0035), minus its HTTP layer.

Support tickets arrived as three mixed files: a service, an attachment store and
two routers. This package holds the first two — the rules about who may read a
ticket, how many may be opened per hour and what happens to an uploaded file.
The routers stayed in ``api/routes/``, where ``Depends`` and status codes live.

- ``service``     — ownership rules, rate budgets, conversation assembly.
- ``attachments`` — validation, storage on the data volume, download answers.

Neither module knows how a ticket is reached over HTTP. They do raise
``HTTPException`` for the cases the plan fixed as status codes (404 for someone
else's ticket, 413 for an oversized body, 429 for an exhausted budget) because
those answers are part of the feature's contract; the alternative was inventing
a second error type that every router would have to translate anyway.
"""
