"""Add deploy_token to services table

Revision ID: 0003_add_deploy_token
Revises: 0002_add_service_env_vars
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_add_deploy_token"
down_revision = "0002_add_service_env_vars"
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("services")]
    if "deploy_token" not in columns:
        op.add_column("services", sa.Column("deploy_token", sa.String(length=64), nullable=True))

def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("services")]
    if "deploy_token" in columns:
        op.drop_column("services", "deploy_token")
