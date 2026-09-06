import Link from "next/link";
import {notFound} from "next/navigation";
import {ArrowLeft,ExternalLink,MapPin,Users} from "lucide-react";
import JobActions from "@/components/JobActions";
import JobFeedback from "@/components/JobFeedback";
import AIAnalysisPanel from "@/components/AIAnalysisPanel";
import ApplicationPackagePanel from "@/components/ApplicationPackagePanel";
import BrowserApplicationPanel from "@/components/BrowserApplicationPanel";
import {getAgentRuns,getAnalysis,getApplicationForm,getApplicationPackage,getEligibility,getJob,getResearch} from "@/lib/server-api";

export default async function JobPage({params}:{params:Promise<{id:string}>}){
  const {id}=await params;
  const [job,analysis,research,runs,pkg,form,eligibility]=await Promise.all([
    getJob(id),getAnalysis(id),getResearch(id),getAgentRuns(id),getApplicationPackage(id),getApplicationForm(id),getEligibility(id),
  ]);
  if(!job)notFound();
  const opportunity=job.opportunity_score;
  return <div className="page-wrap detail-page">
    <Link className="back" href="/dashboard"><ArrowLeft size={16}/> Back to opportunities</Link>
    <header className="detail-header"><div><p className="eyebrow">{job.company}</p><h1>{job.title}</h1><div className="job-meta"><span><MapPin size={14}/>{job.location??"Location unknown"}</span><span>{job.remote_type}</span><span>{job.employment_type??"Type unknown"}</span></div></div><div className="hero-score"><strong>{opportunity?.overall_score??job.fit_score??"—"}</strong><span>OPPORTUNITY</span><em>{opportunity?.recommendation.replaceAll("_"," ")??"ANALYZING"}</em></div></header>
    <section className="recommendation-banner"><div><p className="eyebrow">RECOMMENDED NEXT ACTION</p><h2>{opportunity?.recommendation.replaceAll("_"," ")??"Complete analysis"}</h2><p>{opportunity?.recommendation_reason}</p></div><JobActions jobId={job.id} status={job.application_status}/></section>
    <div className="detail-grid"><div className="detail-main">
      <section className="panel"><p className="panel-label">WHY YOU MATCH</p><h2>Evidence behind the recommendation</h2>{opportunity?.why_you_match.length?opportunity.why_you_match.map(x=><div className="evidence-reason" key={x.reason}><p>{x.reason}</p><span>{x.evidence_ids.join(" · ")||"Evidence linkage pending"}</span></div>):<p>Run scoring and semantic analysis to link match reasons to verified evidence.</p>}</section>
      <section className="panel"><p className="panel-label">REAL GAPS</p><h2>What is missing—and what kind of gap it is</h2>{opportunity?.real_gaps.length?opportunity.real_gaps.map(x=><div className="gap-row" key={x.text}><b>{x.kind.replaceAll("_"," ")}</b><p>{x.text}</p></div>):<p>No material scored gaps have surfaced.</p>}</section>
      <section className="panel"><p className="panel-label">COMPANY & ROLE RESEARCH</p><h2>{research?.company_summary?"What the agent found":"Research not generated yet"}</h2><p>{research?.company_summary??"Generate research when this opportunity is worth deeper attention."}</p>{research?.role_summary?<p>{research.role_summary}</p>:null}</section>
      <section className="panel"><p className="panel-label">PEOPLE TO CONTACT</p><h2><Users size={17}/> Public contact intelligence</h2><p>Contact discovery is prepared as a future extension. It will use public company pages, engineering blogs, GitHub, conferences, and publications—never authenticated LinkedIn scraping.</p></section>
      <section className="panel"><p className="panel-label">APPLICATION PREPARATION</p><h2>Evidence-grounded materials</h2><ApplicationPackagePanel jobId={job.id} initialPackage={pkg}/></section>
      <section className="panel experimental"><p className="panel-label">EXPERIMENTAL APPLICATION AUTOMATION</p><h2>ATS inspection and controlled submission</h2><p>Optional browser automation remains guarded by package review, field validation, duplicate prevention, and explicit submission state.</p><BrowserApplicationPanel jobId={job.id} pkg={pkg} initialForm={form} initialEligibility={eligibility} applicationStatus={job.application_status}/></section>
      <JobFeedback jobId={job.id} initialLabel={job.human_label} initialNotes={job.human_notes} initialFamily={job.role_family}/>
      <details className="technical-details"><summary>Technical details</summary><AIAnalysisPanel jobId={job.id} deterministicScore={job.fit_score} initialAnalysis={analysis} initialResearch={research} initialRuns={runs}/><section className="panel"><h2>Job description</h2><p className="description">{job.description}</p></section></details>
    </div><aside className="detail-aside">
      <section className="panel"><p className="panel-label">CONSTRAINTS</p><h2>Known constraint state</h2>{opportunity?Object.entries(opportunity.constraints).filter(([key])=>key!=="hard_blockers").map(([key,value])=><p className="constraint-row" key={key}><span>{key.replaceAll("_"," ")}</span><b className={String(value).toLowerCase()}>{String(value)}</b></p>):<p>Constraint analysis pending.</p>}</section>
      <section className="panel"><p className="panel-label">SCORE BREAKDOWN</p>{opportunity?[["Technical",opportunity.technical_fit],["Career",opportunity.career_fit],["Research",opportunity.research_fit],["Skills",opportunity.skills_fit],["Freshness",opportunity.freshness_score]].map(([key,value])=><div className="component" key={String(key)}><span>{key}</span><div><i style={{width:`${value??0}%`}}/></div><strong>{value??"?"}</strong></div>):null}</section>
      <section className="panel source-links"><a href={job.source_url} target="_blank" rel="noreferrer">View source <ExternalLink size={14}/></a><a href={job.apply_url} target="_blank" rel="noreferrer">Open application <ExternalLink size={14}/></a></section>
    </aside></div>
  </div>;
}
