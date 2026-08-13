# Alembic migrations

This directory is the version-controlled schema migration layer for Confidence.

Phase 1C.1 establishes the Alembic structure only. It intentionally does not contain an initial schema migration yet and does not replace the existing SQLite startup upgrade path.

Before creating the first revision, verify that Alembic can import the complete SQLAlchemy model metadata and that the migration configuration resolves the application's `DATABASE_URL` without hard-coding credentials.
