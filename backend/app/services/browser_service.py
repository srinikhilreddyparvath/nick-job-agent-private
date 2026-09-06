import hashlib,json
import re
from pathlib import Path
from app.models.browser import *
from app.services.ats_form_adapters import adapter_for
from app.services.field_mapping_service import FieldMappingService

class BrowserBlocked(RuntimeError):pass
class BrowserService:
 def __init__(self):self.mapper=FieldMappingService()
 def inspect_page(self,page,job,package=None):
  url=page.url;adapter=adapter_for(url);captcha_nodes=page.locator("iframe[src*='captcha'], [class*='captcha'], [id*='captcha']");captcha=any(captcha_nodes.nth(i).is_visible() for i in range(captcha_nodes.count()));auth_nodes=page.locator("input[type='password']");auth=any(auth_nodes.nth(i).is_visible() for i in range(auth_nodes.count()))
  # Capture controls before mapping fields. Some dynamic ATS pages re-render
  # their action area while file inputs and custom questions are inspected.
  semantic_submit=page.get_by_role("button",name=re.compile(r"^submit(?: application)?$",re.I))
  try:semantic_submit.first.wait_for(state="visible",timeout=5000)
  except Exception:pass
  submit_nodes=semantic_submit;submits=[]
  for i in range(submit_nodes.count()):
   node=submit_nodes.nth(i);name=((node.inner_text() if node.evaluate("e => e.tagName==='BUTTON'") else node.get_attribute("value")) or node.get_attribute("aria-label") or "").strip();visible=node.is_visible();enabled=node.is_enabled();matches=adapter.submit_name_matches(name)
   if matches:submits.append(SubmitControl(selector_strategy="role_and_accessible_name",locator_value=name,accessible_name=name,element_type=node.evaluate("e => e.tagName.toLowerCase()"),visible=visible,enabled=enabled,actionable=visible and enabled))
  raw=page.locator("input, textarea, select").evaluate_all("""els => { const out=[]; const seen=new Set(); els.forEach((e,i)=>{ const type=e.tagName==='TEXTAREA'?'textarea':e.tagName==='SELECT'?'select':(e.type||'text'); const labelOf=n=>{if(n.getAttribute('aria-label'))return n.getAttribute('aria-label');if(n.labels&&n.labels[0]){const c=n.labels[0].cloneNode(true);c.querySelectorAll('input,textarea,select,button').forEach(x=>x.remove());return c.textContent.trim()}return n.getAttribute('placeholder')||n.name||''}; if(type==='radio'){const key=e.name||e.id||'radio_'+i;if(seen.has('radio:'+key))return;seen.add('radio:'+key);const group=els.filter(x=>x.type==='radio'&&(x.name||x.id)===key);const fs=e.closest('fieldset');const legend=fs&&fs.querySelector('legend');const question=(legend&&legend.textContent.trim())||(fs&&fs.getAttribute('aria-label'))||(fs&&fs.innerText.trim().split(String.fromCharCode(10))[0])||e.getAttribute('aria-label')||key;out.push({id:key,label:question,type:'radio',required:group.some(x=>x.required||x.getAttribute('aria-required')==='true'),options:group.map(x=>labelOf(x)||x.value).filter(Boolean),max:null});return} out.push({id:e.id||e.name||'field_'+i,label:labelOf(e),type,required:e.required||e.getAttribute('aria-required')==='true',options:e.tagName==='SELECT'?[...e.options].map(o=>o.text):[],max:e.maxLength>0?e.maxLength:null})}); return out }""")
  fields=[]
  for x in raw:
   raw_kind="phone" if x["type"]=="tel" else x["type"]
   if raw_kind=="file" and not x["label"] and any(item["type"]=="file" and item["label"] for item in raw):continue
   kind=raw_kind if raw_kind in FieldType._value2member_map_ else "other";field=ApplicationFormField(field_id=x["id"],label=x["label"],normalized_label="",field_type=kind,required=x["required"],options=x["options"],character_limit=x["max"]);fields.append(self.mapper.map(field,package,salary_min=getattr(job,"salary_min",None),salary_max=getattr(job,"salary_max",None)))
  package_valid=bool(package and package.status=="APPROVED" and getattr(package,"review_status",None)=="PASS" and not getattr(package,"requires_human_review",True) and not getattr(package,"unsupported_claims_removed",[]))
  other_required_resolved=all(field.write_allowed and not field.requires_human_review for field in fields if field.required and field.detected_category not in {"truthfulness_certification","electronic_signature"})
  if package_valid and other_required_resolved:
   for index,field in enumerate(fields):
    if field.detected_category in {"truthfulness_certification","electronic_signature"}:fields[index]=self.mapper.map(field,package,certification_allowed=True,salary_min=getattr(job,"salary_min",None),salary_max=getattr(job,"salary_max",None))
  payload=[x.model_dump(mode="json") for x in fields];fp=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
  return ApplicationFormSchema(application_url=url,ats=adapter.ats,company=job.company,job_id=job.id,steps=[page.title()],fields=fields,required_fields=[x.field_id for x in fields if x.required],optional_fields=[x.field_id for x in fields if not x.required],file_uploads=[x.field_id for x in fields if x.field_type=="file"],submit_controls=submits,captcha_detected=captcha,authentication_required=auth,form_fingerprint=fp)
 def actionable_submit_controls(self,form):return [control for control in form.submit_controls if control.actionable and control.visible and control.enabled]
 def readiness_blockers(self,form,package,eligibility=None):
  blockers=[]
  if not package or package.status!="APPROVED" or getattr(package,"review_status",None)!="PASS":blockers.append("PACKAGE_REVIEW_NOT_PASSED")
  if eligibility is not None and str(eligibility.eligibility) in {"BLOCKED","SKIP","NEEDS_REVIEW"}:blockers.extend(eligibility.hard_blockers or [f"ELIGIBILITY_{eligibility.eligibility}"])
  if not form.fields:blockers.append("FORM_NOT_LOADED")
  if form.captcha_detected:blockers.append("BLOCKED_CAPTCHA")
  if form.authentication_required:blockers.append("BLOCKED_AUTH")
  if any(field.required and not self.mapper.validate_write(field) for field in form.fields):blockers.append("REQUIRED_FIELDS_UNRESOLVED")
  if not self.actionable_submit_controls(form):blockers.append("SUBMIT_CONTROL_NOT_FOUND")
  return list(dict.fromkeys(blockers))
 def locate_submit_control(self,page,form):
  controls=self.actionable_submit_controls(form)
  if not controls:return None,None
  control=controls[0];locator=page.get_by_role("button",name=re.compile(rf"^{re.escape(control.accessible_name)}$",re.I))
  return locator.first,control
 def fill_page(self,page,form,package,*,upload_resume=False):
  events=[];blockers=[]
  if form.captcha_detected:return 0,["BLOCKED_CAPTCHA"],[{"event":"CAPTCHA_DETECTED"}]
  if form.authentication_required:return 0,["BLOCKED_AUTH"],[{"event":"AUTH_REQUIRED"}]
  resolved=0
  for field in form.fields:
   if not self.mapper.validate_write(field):
    if field.required:blockers.append(f"UNRESOLVED:{field.label}")
    continue
   locator=page.locator(f"[id={json.dumps(field.field_id)}]") if field.field_id else page.get_by_label(field.label)
   try:
    if field.field_type=="select":
     option=next((x for x in field.options if x.casefold()==field.mapped_answer.casefold()),field.mapped_answer);locator.select_option(label=option)
    elif field.field_type=="radio":
     group=page.locator(f"input[type=radio][name={json.dumps(field.field_id)}]");matched=None
     for index in range(group.count()):
      option=group.nth(index);label=((option.get_attribute("aria-label") or "") or (option.evaluate("e => e.labels&&e.labels[0]?e.labels[0].innerText:''") or "")).strip()
      if label.casefold()==str(field.mapped_answer).casefold():matched=option;break
     if matched is None:raise BrowserBlocked("RADIO_OPTION_NOT_FOUND")
     matched.check()
    elif field.field_type=="checkbox":
     if str(field.mapped_answer).lower() in {"yes","true","checked","agree"}:locator.check()
    elif field.field_type=="file":
     if upload_resume and package.status=="APPROVED" and package.tailored_resume_path:locator.set_input_files(package.tailored_resume_path);events.append({"event":"FILE_UPLOADED","category":"resume","filename":Path(package.tailored_resume_path).name})
     else:continue
    else:locator.fill(field.mapped_answer)
    resolved+=1;events.append({"event":"FIELD_FILLED","category":field.detected_category,"source":field.mapped_answer_source})
   except Exception as exc:
    # An inaccessible duplicate/hidden optional control (common for styled file
    # inputs) must not prevent readiness after the real required control succeeds.
    if field.required:blockers.append(f"WRITE_FAILED:{field.label}")
    events.append({"event":"FORM_VALIDATION_FAILED","category":field.detected_category,"error":type(exc).__name__,"required":field.required})
  return resolved,blockers,events
 def verify_submission(self,page,previous_url,ats=None):
  text=page.locator("body").inner_text().lower();form_present=page.locator("input,textarea,select").count()>0;submit_present=page.get_by_role("button",name=re.compile(r"^submit(?: application)?$",re.I)).count()>0
  markers=page.locator("[role=status], [data-testid*='success'], [class*='success']");marker_text=" ".join((markers.nth(i).inner_text() or "").strip().lower() for i in range(markers.count()) if markers.nth(i).is_visible())
  adapter=adapter_for(previous_url);confirmed,signals=adapter.confirmation(url=page.url,previous_url=previous_url,text=text,form_present=form_present,submit_present=submit_present,marker_text=marker_text)
  return confirmed,{"confirmation_url":page.url if confirmed else None,"confirmation_text":"; ".join(signals) if confirmed else None,"signals":signals,"form_present":form_present,"submit_present":submit_present}
