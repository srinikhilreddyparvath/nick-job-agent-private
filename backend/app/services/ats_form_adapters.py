import re

class BaseFormAdapter:
 ats="generic"
 hosts=()
 def matches(self,url):return any(x in url.lower() for x in self.hosts)
 def stable_selectors(self):return ["label","input[name]","textarea[name]","select[name]","[role=radio]","[role=checkbox]"]
 def submit_name_matches(self,name):return bool(re.fullmatch(r"\s*submit(?:\s+application)?\s*",name or "",re.I))
 def confirmation(self,*,url,previous_url,text,form_present,submit_present,marker_text):
  phrases=("application submitted","thank you for applying","thanks for applying","application received")
  matched=next((phrase for phrase in phrases if phrase in text),None);signals=[]
  if matched:signals.append(f"success_text:{matched}")
  if marker_text:signals.append("semantic_success_marker")
  confirmed=bool(matched or marker_text)
  return confirmed,signals
class AshbyFormAdapter(BaseFormAdapter):
 ats="ashby";hosts=("ashbyhq.com",)
 def confirmation(self,*,url,previous_url,text,form_present,submit_present,marker_text):
  confirmed,signals=super().confirmation(url=url,previous_url=previous_url,text=text,form_present=form_present,submit_present=submit_present,marker_text=marker_text)
  if re.search(r"/(?:submitted|thank-you|application-submitted)(?:[/?#]|$)",url,re.I):signals.append("ashby_success_url");confirmed=True
  if not form_present and not submit_present:signals.append("ashby_form_and_submit_removed")
  # Form disappearance alone is not enough; pair it with an explicit success
  # marker/text or a known Ashby success route.
  return confirmed,signals
class GreenhouseFormAdapter(BaseFormAdapter):ats="greenhouse";hosts=("greenhouse.io","greenhouse.com")
class LeverFormAdapter(BaseFormAdapter):ats="lever";hosts=("lever.co",)
class GenericFormAdapter(BaseFormAdapter):pass
ADAPTERS=[AshbyFormAdapter(),GreenhouseFormAdapter(),LeverFormAdapter(),GenericFormAdapter()]
def adapter_for(url):return next((x for x in ADAPTERS if x.matches(url)),ADAPTERS[-1])
