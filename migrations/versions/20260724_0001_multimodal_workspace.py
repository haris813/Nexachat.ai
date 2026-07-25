"""Create the NexaChat multimodal workspace schema.

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""

from alembic import op

revision = "20260724_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The project predates Alembic and may already contain the legacy chat
    # tables. create_all is intentionally idempotent here so both an existing
    # SQLite demo database and a fresh PostgreSQL database can be stamped safely.
    from app.extensions import db
    from app import models  # noqa: F401

    db.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Preserve user conversations and generated artifacts on downgrade.
    # Destructive schema rollback is intentionally an operator-managed backup
    # and restore operation; see DEPLOYMENT.md.
    pass
