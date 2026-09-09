"""Add job-grounded public contact records."""
from alembic import op
from app.db.models import ContactRecord

revision="20260906_0002"
down_revision="20260902_0001"
branch_labels=None
depends_on=None

def upgrade():
    ContactRecord.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():
    ContactRecord.__table__.drop(op.get_bind(),checkfirst=True)
