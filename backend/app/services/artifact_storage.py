from abc import ABC,abstractmethod
from pathlib import Path
import hashlib,shutil
from app.core.config import get_settings
class ArtifactStorage(ABC):
 @abstractmethod
 def put(self,key,source:Path)->str:...
 @abstractmethod
 def path(self,key)->Path:...
class LocalArtifactStorage(ArtifactStorage):
 def __init__(self,root=None):self.root=Path(root or get_settings().artifact_storage_path).resolve();self.root.mkdir(parents=True,exist_ok=True)
 def put(self,key,source):return self.store(key,source)
 def path(self,key):
  target=(self.root/key).resolve()
  if self.root not in target.parents and target!=self.root:raise ValueError("Invalid artifact key")
  return target
 def store(self,key,source):target=self.path(key);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);return hashlib.sha256(target.read_bytes()).hexdigest()
class S3ArtifactStorage(ArtifactStorage):
 def put(self,key,source):raise NotImplementedError("Configure an S3 adapter in production")
 def path(self,key):raise NotImplementedError("S3 artifacts do not expose local paths")
