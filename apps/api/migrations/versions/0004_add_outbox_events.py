"""Add outbox_events table for transactional outbox pattern

Revision ID: 0004_add_outbox_events
Revises: 0003_add_deploy_token
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_add_outbox_events"
down_revision = "0003_add_deploy_token"
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "outbox_events" not in tables:
        op.create_table(
            "outbox_events",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_outbox_events_status_created", "outbox_events", ["status", "created_at"])

def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "outbox_events" in tables:
        op.drop_index("ix_outbox_events_status_created", table_name="outbox_events")
        op.drop_table("outbox_events")
