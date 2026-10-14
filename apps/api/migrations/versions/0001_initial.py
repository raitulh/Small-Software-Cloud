"""Initial schema snapshot. Future changes must use new incremental revisions."""
from alembic import op
from app import models  # noqa: F401 - register ORM tables and enum types
from app.db.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # This is the initial single-release schema. Freeze this revision after first release.
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
