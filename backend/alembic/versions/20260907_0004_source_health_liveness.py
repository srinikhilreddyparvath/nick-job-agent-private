"""source health and job liveness

Revision ID: 20260907_0004
Revises: 20260906_0003
"""
from alembic import op
import sqlalchemy as sa
revision="20260907_0004";down_revision="20260906_0003";branch_labels=None;depends_on=None
def upgrade():
    columns=(sa.Column("last_attempt_at",sa.DateTime(timezone=True)),sa.Column("last_failure_at",sa.DateTime(timezone=True)),sa.Column("failure_type",sa.String(40)),sa.Column("consecutive_failures",sa.Integer,nullable=False,server_default="0"),sa.Column("average_latency_ms",sa.Float),sa.Column("last_job_count",sa.Integer,nullable=False,server_default="0"),sa.Column("retry_after",sa.DateTime(timezone=True)),sa.Column("health_status",sa.String(40),nullable=False,server_default="UNKNOWN"),sa.Column("disabled_reason",sa.Text))
    # The baseline migration creates the current model for a brand-new install,
    # while existing installations may still need these columns added. Inspect
    # the live schema so both upgrade paths remain valid.
    existing={column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_sources")}
    for column in columns:
        if column.name not in existing:op.add_column("job_sources",column)
def downgrade():
    existing={column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_sources")}
    for name in ("disabled_reason","health_status","retry_after","last_job_count","average_latency_ms","consecutive_failures","failure_type","last_failure_at","last_attempt_at"):
        if name in existing:op.drop_column("job_sources",name)
