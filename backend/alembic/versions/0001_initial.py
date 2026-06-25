"""initial schema (all current tables)

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-25
"""
from alembic import op

from app import models  # noqa: F401  (register tables on Base.metadata)
from app.database import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create every table on the models' metadata. checkfirst=True keeps this safe
    # to run alongside the app's startup create_all (idempotent).
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
