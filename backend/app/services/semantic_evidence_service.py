import hashlib
import json
import math

from sqlalchemy import delete,select
from sqlalchemy.orm import Session

from app.db.models import EvidenceEmbeddingRecord
from app.models.semantic import RetrievalMethod,SemanticEvidenceResult
from app.services.embedding_service import EmbeddingError,EmbeddingService,configured_embedding_service
from app.services.evidence_service import EvidenceService
from app.services.candidate_context_service import current_context


def evidence_version(records)->str:
    payload=[{"id":x.id,"statement":x.statement,"verified":x.verified,"skills":x.skills,"domains":x.domains,"source_reference":x.source_reference} for x in sorted(records,key=lambda x:x.id)]
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
def cosine(a,b):
    denom=math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b));return sum(x*y for x,y in zip(a,b))/denom if denom else 0
class SemanticEvidenceIndex:
    def __init__(self,evidence:EvidenceService|None=None,embeddings:EmbeddingService|None=None):self.evidence=evidence or EvidenceService();self.embeddings=embeddings or configured_embedding_service()
    @property
    def version(self):return hashlib.sha256((current_context().key + evidence_version(self.evidence.all())).encode()).hexdigest()
    def reindex(self,db:Session,force:bool=False)->dict:
        records=self.evidence.all();version=self.version
        existing=db.scalar(select(EvidenceEmbeddingRecord.id).where(EvidenceEmbeddingRecord.evidence_version==version,EvidenceEmbeddingRecord.provider==self.embeddings.provider.name,EvidenceEmbeddingRecord.model==self.embeddings.provider.model).limit(1))
        if existing and not force:return {"status":"current","evidence_version":version,"indexed":len(records)}
        vectors=self.embeddings.embed_batch([x.statement+" "+" ".join(x.skills+x.domains) for x in records]);db.execute(delete(EvidenceEmbeddingRecord).where(EvidenceEmbeddingRecord.provider==self.embeddings.provider.name,EvidenceEmbeddingRecord.model==self.embeddings.provider.model))
        for record,vector in zip(records,vectors):db.add(EvidenceEmbeddingRecord(evidence_id=record.id,evidence_version=version,provider=vector.provider,model=vector.model,embedding_version=vector.embedding_version,vector=vector.vector,generated_at=vector.generated_at))
        db.commit();return {"status":"indexed","evidence_version":version,"indexed":len(records)}
    def search(self,db:Session,query:str,limit:int=10,**filters)->list[SemanticEvidenceResult]:
        self.reindex(db);query_vector=self.embeddings.embed_text(query).vector;allowed={x.id:x for x in self.evidence.search(**filters)}
        rows=db.scalars(select(EvidenceEmbeddingRecord).where(EvidenceEmbeddingRecord.evidence_version==self.version,EvidenceEmbeddingRecord.provider==self.embeddings.provider.name,EvidenceEmbeddingRecord.model==self.embeddings.provider.model)).all()
        scored=[SemanticEvidenceResult(evidence_id=row.evidence_id,statement=allowed[row.evidence_id].statement,score=max(0,min(1,(cosine(query_vector,row.vector)+1)/2)),retrieval_method=RetrievalMethod.semantic) for row in rows if row.evidence_id in allowed]
        return sorted(scored,key=lambda x:x.score,reverse=True)[:limit]
