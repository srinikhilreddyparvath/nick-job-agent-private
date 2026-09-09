"""Scope existing evaluation and application abstractions to candidates.

Legacy ownerless rows stay historical. Never infer ownership from whichever
resume happens to be active at migration time. Shared job facts are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0006"
down_revision = "20260909_0005"
branch_labels = None
depends_on = None

EVALUATIONS = ("job_scores", "semantic_analyses", "agent_runs", "evidence_embeddings", "company_research")
ARTIFACTS = ("applications", "application_events", "job_feedback", "application_packages", "approved_answer_history",
             "application_forms", "browser_application_events", "application_queue_items", "application_receipts",
             "morning_reports", "application_outcomes", "job_exclusions", "discovery_leads", "contact_intelligence", "contact_discovery_runs")
GLOBAL_FIT_FIELDS = ("family_fit_score", "family_component_scores", "family_recommendation", "family_strengths",
                     "family_gaps", "matched_evidence_ids", "career_transition_flag", "career_transition_notes")


def upgrade():
    from app.db.models import Base
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    # Use the declared types/defaults, but no runtime candidate values.
    for name in (*EVALUATIONS, *ARTIFACTS):
        if name not in existing_tables: continue
        model = Base.metadata.tables[name]
        columns = {c["name"] for c in sa.inspect(bind).get_columns(name)}
        for column in model.columns:
            if column.name in columns: continue
            default = None
            if column.name == "updated_at": default = sa.func.now()
            if column.name in ("constraint_results", "family_component_scores"): default = sa.text("'{}'")
            if column.name in ("family_strengths", "family_gaps", "matched_evidence_ids"): default = sa.text("'[]'")
            if column.name == "career_transition_flag": default = sa.false()
            identity = [sa.Identity()] if column.primary_key else []
            op.add_column(name, sa.Column(column.name, column.type, *identity, nullable=column.nullable, server_default=default))
        primary = sa.inspect(bind).get_pk_constraint(name)
        target_primary = [c.name for c in model.primary_key.columns]
        if primary["constrained_columns"] != target_primary:
            op.drop_constraint(primary["name"], name, type_="primary")
            op.create_primary_key(primary["name"], name, target_primary)
        # Previously unique job_id prevented a second candidate's application.
        for constraint in sa.inspect(bind).get_unique_constraints(name):
            if constraint["column_names"] == ["job_id"] or (name == "discovery_leads" and constraint["column_names"] == ["url"]):
                op.drop_constraint(constraint["name"], name, type_="unique")
        for index in sa.inspect(bind).get_indexes(name):
            if index.get("unique") and index["column_names"] == ["job_id"] and not index.get("duplicates_constraint"):
                op.drop_index(index["name"], table_name=name)
        current_unique = {c["name"] for c in sa.inspect(bind).get_unique_constraints(name)}
        for constraint in model.constraints:
            if isinstance(constraint, sa.UniqueConstraint) and constraint.name and constraint.name not in current_unique:
                op.create_unique_constraint(constraint.name, name, [c.name for c in constraint.columns])
        current_indexes = {i["name"] for i in sa.inspect(bind).get_indexes(name)}
        for index in model.indexes:
            if index.name not in current_indexes:
                op.create_index(index.name, name, [c.name for c in index.columns], unique=index.unique)
    # These values cannot be assigned a trustworthy owner. Keep the existing
    # score/semantic history unowned; invalidate the unsafe shared copies.
    columns = {c["name"] for c in sa.inspect(bind).get_columns("jobs")}
    for name in GLOBAL_FIT_FIELDS:
        if name in columns: op.drop_column("jobs", name)


def downgrade():
    raise RuntimeError("Candidate isolation cannot be downgraded without reintroducing shared candidate data")
