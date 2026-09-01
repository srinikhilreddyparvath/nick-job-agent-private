import hashlib
import math
import os
import re
from abc import ABC,abstractmethod
from datetime import datetime,timezone

import httpx

from app.core.config import Settings,get_settings
from app.models.semantic import EmbeddingVector


class EmbeddingError(RuntimeError): pass
class EmbeddingProvider(ABC):
    name:str;model:str
    @abstractmethod
    def embed_batch(self,texts:list[str])->list[list[float]]:...
class HashEmbeddingProvider(EmbeddingProvider):
    name="mock"
    def __init__(self,model="hash-embedding-v1",dimensions=128):self.model=model;self.dimensions=dimensions
    def embed_batch(self,texts):
        output=[]
        for text in texts:
            vector=[0.0]*self.dimensions
            for token in re.findall(r"[a-z0-9]+",text.lower()):
                digest=hashlib.sha256(token.encode()).digest();index=int.from_bytes(digest[:4],"big")%self.dimensions;vector[index]+=1 if digest[4]%2 else -1
            norm=math.sqrt(sum(x*x for x in vector)) or 1;output.append([x/norm for x in vector])
        return output
class OpenAIEmbeddingProvider(EmbeddingProvider):
    name="openai"
    def __init__(self,model,api_key=None,timeout=45):self.model=model;self.api_key=api_key or os.getenv("OPENAI_API_KEY");self.timeout=timeout
    def embed_batch(self,texts):
        if not self.api_key:raise EmbeddingError("OPENAI_API_KEY is not configured")
        response=httpx.post("https://api.openai.com/v1/embeddings",headers={"Authorization":f"Bearer {self.api_key}"},json={"model":self.model,"input":texts},timeout=self.timeout);response.raise_for_status();return [item["embedding"] for item in sorted(response.json()["data"],key=lambda x:x["index"])]
class EmbeddingService:
    def __init__(self,provider:EmbeddingProvider):self.provider=provider
    def embed_batch(self,texts:list[str])->list[EmbeddingVector]:
        vectors=self.provider.embed_batch(texts);now=datetime.now(timezone.utc);version=f"{self.provider.name}:{self.provider.model}:v1"
        return [EmbeddingVector(vector=x,provider=self.provider.name,model=self.provider.model,embedding_version=version,generated_at=now) for x in vectors]
    def embed_text(self,text:str)->EmbeddingVector:return self.embed_batch([text])[0]
def configured_embedding_service(settings:Settings|None=None)->EmbeddingService:
    settings=settings or get_settings();provider=settings.embedding_provider or "mock"
    if provider in {"mock","local","hash"}:return EmbeddingService(HashEmbeddingProvider(settings.embedding_model or "hash-embedding-v1"))
    if provider=="openai":return EmbeddingService(OpenAIEmbeddingProvider(settings.embedding_model,timeout=settings.llm_timeout_seconds))
    raise EmbeddingError(f"Unsupported embedding provider: {provider}")
