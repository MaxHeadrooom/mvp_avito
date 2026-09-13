"""Add partner_api_key_hash to establishments.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "establishments",
        sa.Column(
            "partner_api_key_hash",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column("establishments", "partner_api_key_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("establishments", "partner_api_key_hash")