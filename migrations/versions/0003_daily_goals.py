"""Store effective and unmodified daily nutrition goals.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("activity_energy_kcal", sa.Numeric(14, 4), nullable=True),
        sa.Column("consume_activity_energy", sa.Boolean(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "local_date", name="uq_daily_goals_source_local_date"
        ),
    )
    op.create_index("ix_daily_goals_local_date", "daily_goals", ["local_date"])

    op.create_table(
        "daily_goal_values",
        sa.Column("daily_goal_id", sa.Uuid(), nullable=False),
        sa.Column("variant", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["daily_goal_id"], ["daily_goals.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("daily_goal_id", "variant", "code"),
    )

    op.add_column(
        "sync_runs",
        sa.Column("goals_seen", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "sync_runs",
        sa.Column("goals_upserted", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade():
    op.drop_column("sync_runs", "goals_upserted")
    op.drop_column("sync_runs", "goals_seen")
    op.drop_table("daily_goal_values")
    op.drop_index("ix_daily_goals_local_date", table_name="daily_goals")
    op.drop_table("daily_goals")
