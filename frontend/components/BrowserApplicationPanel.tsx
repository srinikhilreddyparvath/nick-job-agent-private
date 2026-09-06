"use client";

import {useRef,useState} from "react";
import {apiError,apiFetch} from "@/lib/client-api";
import {ApplicationForm,ApplicationPackage,BrowserRunResult,EligibilityDecision} from "@/lib/types";

type Readiness={status:string;ready:boolean;reason:string|null};

export function applicationReadiness(pkg:ApplicationPackage|null,form:ApplicationForm|null,result:BrowserRunResult|null,applicationStatus?:string|null):Readiness{
 const status=result?.status??form?.status??"NOT_INSPECTED";
 const canonical=result?.status==="SUBMITTED"||result?.status==="SUBMISSION_UNVERIFIED"?result.status:applicationStatus;
 if(canonical==="SUBMISSION_UNVERIFIED"||canonical==="SUBMITTED")return {status:canonical,ready:false,reason:canonical};
 if(pkg?.status!=="APPROVED")return {status,ready:false,reason:"PACKAGE_NOT_APPROVED"};
 if(result?.blockers.length)return {status,ready:false,reason:result.blockers[0]};
 if(!form?.submit_controls?.some(control=>control.actionable&&control.visible&&control.enabled))return {status:"SUBMIT_CONTROL_NOT_FOUND",ready:false,reason:"SUBMIT_CONTROL_NOT_FOUND"};
 if(status!=="READY_TO_SUBMIT")return {status,ready:false,reason:status};
 return {status,ready:true,reason:null};
}

export default function BrowserApplicationPanel({jobId,pkg,initialForm,initialEligibility,applicationStatus}:{jobId:number;pkg:ApplicationPackage|null;initialForm:ApplicationForm|null;initialEligibility:EligibilityDecision|null;applicationStatus?:string|null}){
 const [form,setForm]=useState(initialForm);const [eligibility,setEligibility]=useState(initialEligibility);const [result,setResult]=useState<BrowserRunResult|null>(null);const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const pending=useRef(false);
 const readiness=applicationReadiness(pkg,form,result,applicationStatus);const packageApproved=pkg?.status==="APPROVED";const required=form?.fields.filter(field=>field.required)??[];const resolvedRequired=required.filter(field=>field.write_allowed&&!field.requires_human_review).length;const submissionLocked=readiness.status==="SUBMISSION_UNVERIFIED"||readiness.status==="SUBMITTED";

 async function action(path:string,body?:object){
  if(pending.current){setMessage("ACTION_ALREADY_IN_PROGRESS");return null}
  if(path==="submit-application"&&!readiness.ready){setMessage(readiness.reason??"APPLICATION_NOT_READY");return null}
  pending.current=true;setBusy(true);setMessage("");
  try{
   const init:RequestInit={method:"POST"};if(body!==undefined){init.headers={"Content-Type":"application/json"};init.body=JSON.stringify(body)}
   const response=await apiFetch(`/jobs/${jobId}/${path}`,init);const data=await response.json();if(!response.ok)throw apiError(response,data.detail);
   if(path==="apply-anyway")setEligibility(data);else{setResult(data);if(data.form)setForm(data.form)}
   return data;
  }catch(error){setMessage(error instanceof Error?error.message:"API_ERROR");return null}
  finally{pending.current=false;setBusy(false)}
 }
 async function resolve(label:string){const answer=window.prompt(`Approved answer for: ${label}`);if(answer===null||!answer.trim())return;const standing=window.confirm("Save as a standing policy? Cancel saves only for this application.");await action("application-form/resolve",{field_label:label,answer:answer.trim(),scope:standing?"SAVE_AS_STANDING_POLICY":"JUST_THIS_APPLICATION"});setMessage("Resolution saved. Inspect the form again to apply it.")}

 return <section className="panel browser-panel"><p className="panel-label">CONTROLLED APPLICATION</p><div className="browser-status"><div><span>Eligibility</span><strong>{eligibility?.eligibility??"CHECKING"}</strong></div><div><span>Package</span><strong>{pkg?.status??"NOT GENERATED"}</strong></div><div><span>Reviewer</span><strong>{pkg?.review_status??"NOT RUN"}</strong></div><div><span>Form</span><strong>{readiness.status}</strong></div></div>
 <p className="guardrail">Fit controls priority, not permission. Truthfulness, required fields, legal policy, CAPTCHA, authentication, and package validation remain hard safeguards.</p>
 <div className="browser-actions"><button type="button" disabled={busy||submissionLocked} onClick={()=>action("apply-anyway",{enabled:true})}>APPLY ANYWAY</button><button type="button" disabled={busy||!pkg} onClick={()=>action("inspect-form",{mode:"INSPECT_ONLY",dry_run:true})}>INSPECT FORM</button><button type="button" disabled={busy||!packageApproved||submissionLocked} onClick={()=>action("fill-application",{mode:"FILL_ONLY",dry_run:true})}>FILL APPLICATION</button>{readiness.ready||submissionLocked?<button type="button" className="danger-action" disabled={busy||submissionLocked} onClick={()=>action("submit-application")}>{busy?"SUBMITTING...":"SUBMIT APPLICATION"}</button>:null}</div>
 {!packageApproved&&pkg?<p className="review-callout">Human approval of the validated package is required before resume upload or field filling.</p>:null}{readiness.ready?<p className="ready-callout">Ready to submit. Review the filled application, then use SUBMIT APPLICATION for the external action.</p>:readiness.status==="SUBMISSION_UNVERIFIED"?<p className="review-callout">The external application was submitted or attempted, but confirmation could not be verified. Do not resubmit until the result is reconciled.</p>:readiness.status==="SUBMITTED"?<p className="ready-callout">Application submitted and confirmation recorded.</p>:<p className="review-callout">Application is not ready: {readiness.reason}{result?.failure_stage?` at ${result.failure_stage}`:""}.</p>}{message?<p className="review-callout" role="alert">{message}</p>:null}
 {form?<details open><summary>APPLICATION FORM · {form.ats.toUpperCase()}</summary><p>{resolvedRequired}/{required.length} required questions resolved · Resume {result?.resume_upload_status==="UPLOADED"?"uploaded":"ready"}</p><div className="field-preview">{form.fields.map(field=><div key={field.field_id}><b>{field.write_allowed&&!field.requires_human_review?"✓":field.requires_human_review?"?":"–"}</b><span>{field.label}{field.required?" *":""}<small>{field.mapped_answer_source??"No approved answer"}</small>{field.mapped_answer?<code>{field.detected_category==="resume"?"Approved tailored resume":field.mapped_answer}</code>:null}</span><em>{field.write_allowed&&!field.requires_human_review?"APPROVED":field.requires_human_review?<button type="button" onClick={()=>resolve(field.label)}>RESOLVE</button>:"OPTIONAL / BLANK"}</em></div>)}</div>{form.captcha_detected?<p className="review-callout">CAPTCHA detected — automation is blocked.</p>:null}{form.authentication_required?<p className="review-callout">Authentication required — automation is blocked.</p>:null}</details>:null}
 </section>;
}
