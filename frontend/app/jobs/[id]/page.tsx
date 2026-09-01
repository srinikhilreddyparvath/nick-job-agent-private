import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink, MapPin } from "lucide-react";
import JobActions from "@/components/JobActions";
import JobFeedback from "@/components/JobFeedback";
import AIAnalysisPanel from "@/components/AIAnalysisPanel";
import { getAgentRuns, getAnalysis, getJob, getResearch } from "@/lib/api";

export default async function JobPage({params}:{params:Promise<{id:string}>}) {
  const {id}=await params; const [job,analysis,research,runs]=await Promise.all([getJob(id),getAnalysis(id),getResearch(id),getAgentRuns(id)]); if(!job) notFound();
  return <div className="page-wrap detail-page">
    <Link className="back" href="/"><ArrowLeft size={16}/> Back to job intelligence</Link>
    <header className="detail-header"><div><p className="eyebrow">{job.company}</p><h1>{job.title}</h1><div className="detail-family"><b>{job.role_family.replaceAll("_"," / ")}</b><span>Confidence {Math.round(job.role_family_confidence*100)}%</span>{job.career_transition_flag?<em>CAREER TRANSITION</em>:null}</div><div className="job-meta"><span><MapPin size={14}/>{job.location??"Not listed"}</span><span>{job.remote_type}</span><span>{job.employment_type??"Employment type not listed"}</span><span>Source: {job.source}</span></div></div><div className={`hero-score score-${job.recommendation??"none"}`}><strong>{job.fit_score??"—"}</strong><span>FAMILY FIT</span><em>{job.recommendation??"unscored"}</em></div></header>
    <JobActions jobId={job.id} status={job.application_status}/>
    <div className="detail-grid"><div className="detail-main">
      <section className="panel"><p className="panel-label">ANALYSIS</p><h2>Why it matches</h2><p>{job.fit_explanation??"Run deterministic scoring to generate an evidence-based fit explanation."}</p><h3>Strengths</h3><ul>{job.strengths.map(x=><li key={x}>{x}</li>)}</ul><h3>Matched skills</h3><div className="chips">{job.matched_skills.length?job.matched_skills.map(x=><span className="positive" key={x}>{x}</span>):<span>No matched skills recorded</span>}</div></section>
      <AIAnalysisPanel jobId={job.id} deterministicScore={job.fit_score} initialAnalysis={analysis} initialResearch={research} initialRuns={runs}/>
      <section className="panel"><p className="panel-label">POSTING</p><h2>Job description</h2><p className="description">{job.description||"No description returned by the source."}</p></section>
      <section className="panel"><h2>Requirements</h2>{job.requirements.length?<ul>{job.requirements.map(x=><li key={x}>{x}</li>)}</ul>:<p>Requirements were not separately structured by the source.</p>}</section>
      <section className="panel"><h2>Preferred qualifications</h2>{job.preferred_qualifications.length?<ul>{job.preferred_qualifications.map(x=><li key={x}>{x}</li>)}</ul>:<p>No separately structured preferred qualifications.</p>}</section>
      {job.career_transition_flag?<section className="panel transition-panel"><p className="panel-label">TRANSFERABLE EVIDENCE / TRANSITION</p><h2>Technically aligned PM opportunity</h2><p>{job.career_transition_notes}</p><div className="chips">{job.matched_evidence_ids.map(x=><span key={x}>{x}</span>)}</div></section>:null}
      <JobFeedback jobId={job.id} initialLabel={job.human_label} initialNotes={job.human_notes} initialFamily={job.role_family}/>
    </div><aside className="detail-aside">
      <section className="panel"><p className="panel-label">FAMILY SCORECARD</p><h2>Component scores</h2>{Object.entries(job.family_component_scores).map(([key,item])=><div className="component" key={key}><span>{key.replaceAll("_"," ")}</span><div><i style={{width:`${item.score}%`}}/></div><strong>{item.score}</strong></div>)}<small>Family-specific deterministic rubric. Unknown inputs remain neutral.</small></section>
      <section className="panel"><p className="panel-label">POTENTIAL GAPS</p><h2>Watch areas</h2>{job.gaps.length?<ul>{job.gaps.map(x=><li key={x}>{x}</li>)}</ul>:<p>No scored gaps recorded.</p>}<h3>Missing skills</h3>{job.missing_skills.length?<ul>{job.missing_skills.map(x=><li key={x}>{x}</li>)}</ul>:<p>No specific missing skills recorded.</p>}</section>
      <section className="panel source-links"><a href={job.source_url} target="_blank" rel="noreferrer">View source <ExternalLink size={14}/></a><a href={job.apply_url} target="_blank" rel="noreferrer">Open application page <ExternalLink size={14}/></a><small>Opening the application page does not submit anything.</small></section>
    </aside></div>
  </div>;
}
