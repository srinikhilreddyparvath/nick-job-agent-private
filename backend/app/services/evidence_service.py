import json
from pathlib import Path

from app.models.profile import EvidenceRecord


class EvidenceService:
    """Deterministic candidate-memory retrieval; semantic search can implement this interface later."""
    def __init__(self,path:Path|None=None):
        self.path=path or Path(__file__).resolve().parents[3]/"data"/"evidence.json"
        self._records=[EvidenceRecord.model_validate(x) for x in json.loads(self.path.read_text(encoding="utf-8"))]
    def get_by_id(self,evidence_id:str)->EvidenceRecord|None: return next((x for x in self._records if x.id==evidence_id),None)
    def search(self,*,company:str|None=None,domains:list[str]|None=None,skills:list[str]|None=None,category:str|None=None,text_query:str|None=None)->list[EvidenceRecord]:
        results=self._records
        if company: results=[x for x in results if company.lower() in (x.company or "").lower()]
        if category: results=[x for x in results if x.category.lower()==category.lower()]
        if domains: results=[x for x in results if all(any(q.lower() in value.lower() for value in x.domains) for q in domains)]
        if skills: results=[x for x in results if all(any(q.lower() in value.lower() for value in x.skills) for q in skills)]
        if text_query:
            query_terms={x for x in text_query.lower().replace("-"," ").split() if len(x)>2}
            results=[x for x in results if query_terms<=set((x.statement+" "+" ".join(x.skills+x.domains)).lower().replace("-"," ").split())]
        return results

