"use client";

import Link from "next/link";
import {useMemo,useState} from "react";
import {ArrowUpRight,Bookmark,BriefcaseBusiness,CircleCheck,Command,MapPin,Search,Sparkles} from "lucide-react";
import FindJobsPanel from "@/components/FindJobsPanel";
import {apiFetch} from "@/lib/client-api";
import {CareerRun,Job,JobList,JobSource} from "@/lib/types";

import {roleFamilyLabel} from "@/lib/role-families";

function money(job:Job){
  if(!job.salary_min&&!job.salary_max)return "Compensation unknown";
  return [job.salary_min,job.salary_max].filter(Boolean).map(x=>`$${Math.round(x!/1000)}k`).join(" - ");
}

function JobCard({job}:{job:Job}){
  const [saved,setSaved]=useState(job.application_status==="shortlisted");
  const [saving,setSaving]=useState(false);
  const opportunity=job.opportunity_score;
  const strengths=(opportunity?.why_you_match.map(x=>x.reason)??job.strengths).slice(0,2);
  const gaps=(opportunity?.real_gaps.map(x=>x.text)??job.gaps).slice(0,2);
  const knownConstraints=opportunity?Object.values(opportunity.constraints).filter(value=>value==="MATCH").length:0;
  async function save(){
    if(saved||saving)return;
    setSaving(true);
    try{const response=await apiFetch(`/jobs/${job.id}/shortlist`,{method:"POST"});if(!response.ok)throw new Error("Unable to save this opportunity");setSaved(true)}finally{setSaving(false)}
  }
  return <article className="job-card">
    <div className="job-card-top"><div className="company-avatar">{job.company.slice(0,2).toUpperCase()}</div><div className="job-heading"><span>{job.company}</span><h2><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2><div className="family-line"><b>{roleFamilyLabel(job.role_family)}</b>{opportunity?<em>{opportunity.recommendation.replaceAll("_"," ")}</em>:null}</div></div><div className="score"><strong>{opportunity?.overall_score??job.fit_score??"-"}</strong><span>OPPORTUNITY</span></div></div>
    <div className="job-meta"><span><MapPin size={14}/>{job.location??"Location unknown"}</span><span><BriefcaseBusiness size={14}/>{job.remote_type}</span><span>{money(job)}</span></div>
    <div className="fit-grid"><div><label>Why you match</label><div className="chips">{strengths.length?strengths.map(x=><span className="positive" key={x}>{x}</span>):<span>Awaiting evidence analysis</span>}</div></div><div><label>Real gaps</label><div className="chips">{gaps.length?gaps.map(x=><span key={x}>{x}</span>):<span>No critical gaps surfaced</span>}</div></div></div>
    <div className="job-footer"><span>{opportunity?.confidence?`${Math.round(opportunity.confidence*100)}% confidence · ${knownConstraints} known constraints matched`:opportunity?.recommendation_reason??"Analysis pending"}</span><div className="card-actions"><button type="button" onClick={save} disabled={saved||saving}><Bookmark size={14}/>{saved?"Saved":saving?"Saving...":"Save"}</button><Link href={`/jobs/${job.id}`}>View analysis <ArrowUpRight size={15}/></Link><a href={job.apply_url} target="_blank" rel="noreferrer">View Job <ArrowUpRight size={15}/></a></div></div>
  </article>;
}

export default function Dashboard({data,referenceDate,sources,latestRun}:{data:JobList;referenceDate:string;sources:JobSource[];latestRun:CareerRun|null}){
  const [family,setFamily]=useState<string>("ALL");
  const families=["ALL",...new Set(data.items.filter(job=>job.fit_score!==null).map(job=>job.role_family))];
  const [query,setQuery]=useState("");
  const jobs=useMemo(()=>data.items.filter(x=>(family==="ALL"||x.role_family===family)&&`${x.company} ${x.title}`.toLowerCase().includes(query.toLowerCase())),[data.items,family,query]);
  const metrics=[
    {label:"Jobs evaluated",value:data.total,icon:Search},
    {label:"New today",value:data.items.filter(x=>x.discovered_at.slice(0,10)===referenceDate).length,icon:CircleCheck},
    {label:"Strong opportunities",value:data.items.filter(x=>(x.opportunity_score?.overall_score??0)>=75).length,icon:Command},
    {label:"Saved",value:data.items.filter(x=>x.application_status==="shortlisted").length,icon:Sparkles},
    {label:"Applied",value:data.items.filter(x=>x.application_status==="SUBMITTED").length,icon:BriefcaseBusiness},
  ];
  return <div className="page-wrap">
    <header className="topbar"><div><p className="eyebrow">PERSONAL OPPORTUNITY RADAR</p><h1>Jobs worth your attention</h1><p>Ranked by verified evidence, constraints, freshness, and career value.</p></div><Link className="cta compact" href="/ingest">Add a job</Link></header>
    <FindJobsPanel sources={sources.filter(source=>source.enabled)} initialRun={latestRun}/>
    <section className="metric-grid">{metrics.map(({label,value,icon:Icon})=><article key={label}><Icon size={17}/><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="family-tabs">{families.map(x=><button type="button" className={x===family?"active":""} onClick={()=>setFamily(x)} key={x}>{x==="ALL"?"ALL":roleFamilyLabel(x)}</button>)}</section>
    <section className="toolbar"><div><h2>Ranked opportunities</h2><small>Fit controls priority, not permission</small></div><label className="search"><Search size={16}/><input aria-label="Search opportunities" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search roles or companies"/></label></section>
    <section className="job-list">{jobs.length?jobs.map(x=><JobCard job={x} key={x.id}/>):<div className="empty-state"><Search size={24}/><h2>No opportunities yet</h2><p>Use Find Jobs to search the starter employer universe. Adding a specific company is optional.</p></div>}</section>
  </div>;
}
