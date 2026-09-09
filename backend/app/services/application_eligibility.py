from app.models.browser import Eligibility,EligibilityDecision

class ApplicationEligibilityPolicy:
 def evaluate(self,job,package=None,*,manual_override=False,shortlisted=False,hard_blockers=None,company_priority="NORMAL"):
  blockers=list(hard_blockers or [])
  score=float(job.fit_score or job.family_fit_score or 0);relevant=job.role_family != "UNKNOWN"
  priority=score+(20 if shortlisted else 0)+(15 if manual_override else 0)+({"HIGH":10,"NORMAL":0,"LOW":-5}.get(company_priority,0))
  if blockers:return EligibilityDecision(eligibility=Eligibility.blocked,priority=priority,reasons=["Genuine safety or completion blocker"],hard_blockers=blockers,manual_override=manual_override)
  if manual_override:return EligibilityDecision(eligibility=Eligibility.eligible,priority=priority,reasons=["Manual APPLY ANYWAY override"],manual_override=True)
  if not relevant:return EligibilityDecision(eligibility=Eligibility.skip,priority=priority,reasons=["Role is outside configured career families"])
  if package and package.status in {"REVIEW_REQUIRED","STALE","GENERATION_FAILED","REJECTED"}:return EligibilityDecision(eligibility=Eligibility.needs_review,priority=priority,reasons=["Application package requires review"])
  if score<50:return EligibilityDecision(eligibility=Eligibility.eligible_low_confidence,priority=priority,reasons=["Relevant role; low score affects priority only"])
  return EligibilityDecision(eligibility=Eligibility.eligible,priority=priority,reasons=["Relevant role; fit score controls queue order, not eligibility"])

