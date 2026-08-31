import hashlib,re

CORPORATE_SUFFIXES={"inc","incorporated","llc","ltd","limited","corp","corporation","co","company"}
def normalize_company(value:str)->str:
    words=[w for w in re.findall(r"[a-z0-9]+",value.lower()) if w not in CORPORATE_SUFFIXES]
    return " ".join(words).strip()
def normalize_location(value:str|None,remote_type:str|None=None)->str:
    text=(value or "").lower(); remote=(remote_type or "").lower()
    if remote=="remote" or "remote" in text: return "Remote US" if any(x in text for x in ("us","united states","usa")) else "Remote"
    if "san francisco" in text: return "San Francisco"
    if any(x in text for x in ("bay area","sf bay")): return "San Francisco Bay Area"
    if any(x in text for x in ("san jose","santa clara","sunnyvale","mountain view","cupertino")): return "South Bay"
    if any(x in text for x in ("palo alto","redwood city","san mateo","menlo park")): return "Peninsula"
    if any(x in text for x in ("oakland","berkeley","fremont","east bay")): return "East Bay"
    return (value or "Unknown").strip()
def description_fingerprint(text:str)->str:
    normalized=" ".join(re.findall(r"[a-z0-9]+",text.lower()))
    return hashlib.sha256(normalized[:12000].encode()).hexdigest()

