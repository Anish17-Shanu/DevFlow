"""Baseline schema for DevFlow 2.0.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-29
"""

from alembic import op

from backend.core.database import Base
from backend.models import entities  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
