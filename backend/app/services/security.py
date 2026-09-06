import re
from cryptography.fernet import Fernet
from app.core.config import get_settings
def redact(value:str)->str:
 value=re.sub(r"[\w.+-]+@[\w.-]+","[REDACTED_EMAIL]",value);value=re.sub(r"\+?\d[\d ()-]{8,}\d","[REDACTED_PHONE]",value);return value
class EncryptionService:
 def __init__(self,key=None):self.key=key or (get_settings().encryption_key.get_secret_value() if get_settings().encryption_key else None);self.fernet=Fernet(self.key.encode() if isinstance(self.key,str) else self.key) if self.key else None
 def encrypt(self,value):
  if not self.fernet:raise RuntimeError("ENCRYPTION_KEY is not configured")
  return self.fernet.encrypt(value.encode()).decode()
 def decrypt(self,value):
  if not self.fernet:raise RuntimeError("ENCRYPTION_KEY is not configured")
  return self.fernet.decrypt(value.encode()).decode()
