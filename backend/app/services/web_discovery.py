from abc import ABC,abstractmethod
from dataclasses import dataclass
from app.core.config import get_settings
@dataclass(frozen=True)
class DiscoveryLead:url:str;title:str|None=None;company:str|None=None
class WebJobDiscoveryProvider(ABC):
 @abstractmethod
 def discover(self,queries:list[str],max_urls:int)->list[DiscoveryLead]:...
class DisabledWebJobDiscoveryProvider(WebJobDiscoveryProvider):
 def discover(self,queries,max_urls):return []
class MockWebJobDiscoveryProvider(WebJobDiscoveryProvider):
 def __init__(self,leads=None):self.leads=leads or []
 def discover(self,queries,max_urls):return self.leads[:max_urls]
class WebDiscoveryService:
 def __init__(self,provider=None,settings=None):self.settings=settings or get_settings();self.provider=provider or DisabledWebJobDiscoveryProvider()
 def run(self,queries):
  if not self.settings.web_discovery_enabled:return {"status":"disabled","leads":[]}
  bounded=queries[:self.settings.web_discovery_queries_per_run];leads=self.provider.discover(bounded,self.settings.web_discovery_max_urls_per_run);return {"status":"completed","leads":leads,"requires_url_verification":True}
