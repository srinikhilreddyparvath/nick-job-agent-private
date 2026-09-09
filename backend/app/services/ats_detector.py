import re
from urllib.parse import urlparse
import httpx
from app.models.detection import AtsDetectionResult

PATTERNS=[
 ("greenhouse",r"(?:boards|job-boards)\.greenhouse\.io/([^/?#\s\"'<>]+)"),("lever",r"jobs\.lever\.co/([^/?#\s\"'<>]+)"),("ashby",r"jobs\.ashbyhq\.com/([^/?#\s\"'<>]+)"),("smartrecruiters",r"jobs\.smartrecruiters\.com/([^/?#\s\"'<>]+)"),("workday",r"([a-z0-9-]+)\.(?:wd\d+\.)?myworkdayjobs\.com/([^/?#\s\"'<>]+)"),("workable",r"apply\.workable\.com/([^/?#\s\"'<>]+)"),("bamboohr",r"([a-z0-9-]+)\.bamboohr\.com"),("teamtailor",r"([a-z0-9-]+)\.teamtailor\.com"),("recruitee",r"([a-z0-9-]+)\.recruitee\.com"),("icims",r"careers-[^/]+\.icims\.com"),("jobvite",r"jobs\.jobvite\.com/([^/?#\s\"'<>]+)"),("successfactors",r"career\d*\.successfactors\.(?:com|eu)")]
class AtsDetector:
 def detect(self,company:str,careers_url:str,html:str|None=None,final_url:str|None=None)->AtsDetectionResult:
    detected_urls=[]
    if html is None:
      try:
        response=httpx.get(careers_url,timeout=15,follow_redirects=True,headers={"User-Agent":"CareerIntelligenceAgent/0.1"}); response.raise_for_status(); html=response.text; final_url=str(response.url)
      except Exception as exc:
        return AtsDetectionResult(detected_ats="unknown",confidence=0,board_identifier=None,reasons=[f"Careers page could not be inspected: {exc}"],recommended_source_configuration={"company":company,"ats_type":"generic_company_site","board_identifier":careers_url,"careers_url":careers_url})
    haystack=" ".join([careers_url,final_url or "",html or ""])
    for ats,pattern in PATTERNS:
      match=re.search(pattern,haystack,re.I)
      if match:
        url_match=re.search(r'https?://[^"\'\s<>]+',match.string[max(0,match.start()-20):match.end()+100]); identifier=match.group(1) if match.lastindex else None
        if ats=="workday" and match.lastindex and match.lastindex>=2: identifier=f"{match.group(1)}|{match.group(2)}|{(final_url or careers_url).split('/'+match.group(2))[0]}"
        detected_urls=[final_url or careers_url]; return AtsDetectionResult(detected_ats=ats,confidence=.95,board_identifier=identifier,detected_urls=detected_urls,reasons=[f"Matched known {ats} host pattern"],recommended_source_configuration={"company":company,"ats_type":ats,"board_identifier":identifier or careers_url,"careers_url":careers_url})
    if "JobPosting" in (html or ""): return AtsDetectionResult(detected_ats="generic_company_site",confidence=.8,board_identifier=careers_url,detected_urls=[final_url or careers_url],reasons=["Found schema.org JobPosting structured data"],recommended_source_configuration={"company":company,"ats_type":"generic_company_site","board_identifier":careers_url,"careers_url":careers_url})
    return AtsDetectionResult(detected_ats="generic_company_site",confidence=.4,board_identifier=careers_url,detected_urls=[final_url or careers_url],reasons=["No known ATS host; conservative generic-site configuration"],recommended_source_configuration={"company":company,"ats_type":"generic_company_site","board_identifier":careers_url,"careers_url":careers_url})
