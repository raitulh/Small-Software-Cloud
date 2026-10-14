"""Add service_env_vars table

Revision ID: 0002_add_service_env_vars
Revises: 0001_initial
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_service_env_vars"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    # Safely create only if not existing
    inspector = sa.inspect(conn)
    if "service_env_vars" not in inspector.get_table_names():
        op.create_table(
            "service_env_vars",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("service_id", sa.Uuid(), nullable=False),
            sa.Column("key", sa.String(length=128), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("service_id", "key", name="uq_service_env_var_key")
        )
        op.create_index(op.f("ix_service_env_vars_service_id"), "service_env_vars", ["service_id"], unique=False)

def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "service_env_vars" in inspector.get_table_names():
        op.drop_index(op.f("ix_service_env_vars_service_id"), table_name="service_env_vars")
        op.drop_table("service_env_vars")
