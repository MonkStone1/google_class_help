"""The mapped SQLAlchemy models, one module per bounded context (ADR-0039).

The cache tables, the accounts, the tickets and the administrator registry are
four different lifecycles with four different owners, so they are four modules
rather than one file that every importer had to load. Nothing is re-exported
here on purpose: ``from db.models.classroom import Course`` says which table a
query touches, and adding a name to this package would make that invisible.

``Base`` itself lives in ``db.session`` — the declarative base belongs to the
engine, not to any one group of tables.
"""
