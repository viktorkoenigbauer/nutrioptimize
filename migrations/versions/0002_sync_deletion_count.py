"""Record deletions reconciled during an authoritative source sync.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sync_runs",
        sa.Column("items_deleted", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade():
    op.drop_column("sync_runs", "items_deleted")
