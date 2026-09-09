"""Add bounded public contact discovery run telemetry."""

from alembic import op

from app.db.models import ContactDiscoveryRunRecord

revision = "20260906_0003"
down_revision = "20260906_0002"
branch_labels = None
depends_on = None


def upgrade():
    ContactDiscoveryRunRecord.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    ContactDiscoveryRunRecord.__table__.drop(op.get_bind(), checkfirst=True)
