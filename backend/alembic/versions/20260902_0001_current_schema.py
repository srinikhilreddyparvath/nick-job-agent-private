"""Current application schema baseline."""
from alembic import op
from app.db.database import Base
from app.db import models  # noqa:F401
revision="20260902_0001";down_revision=None;branch_labels=None;depends_on=None
def upgrade():Base.metadata.create_all(bind=op.get_bind(),checkfirst=True)
def downgrade():Base.metadata.drop_all(bind=op.get_bind(),checkfirst=True)
