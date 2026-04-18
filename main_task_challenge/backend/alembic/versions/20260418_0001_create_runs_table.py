"""Create runs table

Revision ID: 20260418_0001
Revises:
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260418_0001"
down_revision = None
branch_labels = None
depends_on = None


run_status_enum = sa.Enum(
    "created",
    "queued",
    "processing",
    "completed",
    "failed",
    name="run_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    run_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", run_status_enum, nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("log_path", sa.String(length=512), nullable=False),
        sa.Column("ground_truth_path", sa.String(length=512), nullable=True),
        sa.Column("start_stage", sa.String(length=32), nullable=False),
        sa.Column("end_stage", sa.String(length=32), nullable=False),
        sa.Column("fallback_end_stage", sa.String(length=32), nullable=True),
        sa.Column("result_csv_path", sa.String(length=512), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=True),
        sa.Column("endpoint_error_m", sa.Float(), nullable=True),
        sa.Column("rms_crosstrack_error_m", sa.Float(), nullable=True),
        sa.Column("cpu_time_sec", sa.Float(), nullable=True),
        sa.Column("wall_time_sec", sa.Float(), nullable=True),
        sa.Column("points_per_sec", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_task_id", "runs", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runs_task_id", table_name="runs")
    op.drop_table("runs")
    bind = op.get_bind()
    run_status_enum.drop(bind, checkfirst=True)
