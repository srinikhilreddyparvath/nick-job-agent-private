"""Allow real-world provider-controlled job text.

Revision ID: 20260909_0005
Revises: 20260907_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0005"
down_revision = "20260907_0004"
branch_labels = None
depends_on = None

TEXT_COLUMNS = (
    "external_id",
    "company",
    "title",
    "normalized_title",
    "location",
    "raw_company",
    "canonical_company",
    "normalized_location",
)


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "jobs" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("jobs")}
    for name in TEXT_COLUMNS:
        current = columns.get(name, {}).get("type")
        if current is not None and not isinstance(current, sa.Text):
            op.alter_column("jobs", name, existing_type=current, type_=sa.Text())


def downgrade():
    # Downgrading these columns could destroy provider data that is valid under
    # the current schema. Keep the durable text representation intact.
    pass
