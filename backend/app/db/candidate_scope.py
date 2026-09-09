"""Default-deny ownership for every ORM candidate artifact query and write.

NULL legacy owners remain historical and are never guessed. Global jobs and
sources are deliberately outside this scope. Evaluation services also validate
their captured context before persistence to reject mid-run profile changes.
"""
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.db.models import CandidateOwned, EvaluationOwned, JobScoreRecord, SemanticAnalysisRecord
from app.services.candidate_context_service import current_context


@event.listens_for(Session, "do_orm_execute")
def scope_candidate_rows(execute_state):
    if execute_state.execution_options.get("candidate_history_audit"):
        return
    context = current_context()
    owner = context.profile_id
    key = context.key
    if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(CandidateOwned, lambda row: row.candidate_profile_id == owner, include_aliases=True),
            with_loader_criteria(EvaluationOwned, lambda row: row.candidate_context_key == key, include_aliases=True),
        )


@event.listens_for(Session, "before_flush")
def validate_candidate_writes(session, flush_context, instances):
    context = current_context()
    for row in [*session.new, *session.dirty]:
        if not isinstance(row, CandidateOwned):
            continue
        if row.candidate_profile_id is None and row in session.new:
            row.candidate_profile_id = context.profile_id
        if row.candidate_profile_id != context.profile_id:
            raise ValueError("Candidate artifact ownership mismatch")
        if isinstance(row, EvaluationOwned):
            if row.candidate_context_key is None and row in session.new:
                for name, value in context.ownership().items():
                    setattr(row, name, value)
            if row.candidate_context_key != context.key:
                raise ValueError("Candidate changed during evaluation")
        if isinstance(row, JobScoreRecord):
            context.validate_evidence(row.matched_evidence_ids)
        if isinstance(row, SemanticAnalysisRecord):
            report = row.report_json or {}
            context.validate_evidence(report.get("evidence_ids", []))
            for strength in report.get("strengths", []):
                if isinstance(strength, dict):
                    context.validate_evidence(strength.get("evidence_ids", []))
