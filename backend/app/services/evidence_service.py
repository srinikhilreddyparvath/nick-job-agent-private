import json
from pathlib import Path

from app.models.profile import EvidenceRecord
from app.services.profile_service import _configured_path
from app.core.config import get_settings


class EvidenceService:
    """Canonical verified evidence retrieval with deterministic and optional semantic paths."""
    def __init__(self,path:Path|None=None):
        self.path=path or _configured_path(get_settings().candidate_evidence_path,"evidence.example.json")
        self._records=[EvidenceRecord.model_validate(x) for x in json.loads(self.path.read_text(encoding="utf-8"))] if self.path.exists() else []
    def get_by_id(self,evidence_id:str)->EvidenceRecord|None: return next((x for x in self._records if x.id==evidence_id),None)
    def all(self)->list[EvidenceRecord]:return list(self._records)
    def search(self,*,company:str|None=None,domains:list[str]|None=None,skills:list[str]|None=None,category:str|None=None,role:str|None=None,text_query:str|None=None)->list[EvidenceRecord]:
        results=self._records
        if company: results=[x for x in results if company.lower() in (x.company or "").lower()]
        if category: results=[x for x in results if x.category.lower()==category.lower()]
        if role: results=[x for x in results if role.lower() in (x.role or "").lower()]
        if domains: results=[x for x in results if all(any(q.lower() in value.lower() for value in x.domains) for q in domains)]
        if skills: results=[x for x in results if all(any(q.lower() in value.lower() for value in x.skills) for q in skills)]
        if text_query:
            query_terms={x for x in text_query.lower().replace("-"," ").split() if len(x)>2}
            results=[x for x in results if query_terms<=set((x.statement+" "+" ".join(x.skills+x.domains)).lower().replace("-"," ").split())]
        return results
    def search_semantic(self,db,semantic_query:str,limit:int=10,embedding_service=None,**filters):
        from app.services.semantic_evidence_service import SemanticEvidenceIndex
        try:return SemanticEvidenceIndex(self,embedding_service).search(db,semantic_query,limit,**filters)
        except Exception:return []
    def search_hybrid(self,db,semantic_query:str,limit:int=10,embedding_service=None,**filters):
        from app.models.semantic import RetrievalMethod,SemanticEvidenceResult
        semantic=self.search_semantic(db,semantic_query,limit*2,embedding_service,**filters);deterministic=self.search(text_query=semantic_query,**filters);scores={x.evidence_id:x.score*.7 for x in semantic};statements={x.evidence_id:x.statement for x in semantic}
        for item in deterministic:scores[item.id]=min(1,scores.get(item.id,0)+.3);statements[item.id]=item.statement
        return [SemanticEvidenceResult(evidence_id=k,statement=statements[k],score=round(v,4),retrieval_method=RetrievalMethod.hybrid) for k,v in sorted(scores.items(),key=lambda x:x[1],reverse=True)[:limit]]
