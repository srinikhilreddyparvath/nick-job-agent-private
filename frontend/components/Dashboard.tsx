"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowUpRight, BriefcaseBusiness, CircleCheck, Command, MapPin, Search, Sparkles } from "lucide-react";
import { Job, JobList, Recommendation } from "@/lib/types";

const filters = ["all", "exceptional", "strong", "possible", "skipped"] as const;
const labels: Record<string,string> = {all:"All roles", exceptional:"Exceptional", strong:"Strong", possible:"Possible", skipped:"Skipped"};
const families=["ALL","RESEARCH_AI","DATA_SCIENCE","PRODUCT_MANAGEMENT"] as const;
const familyLabels:Record<string,string>={ALL:"ALL",RESEARCH_AI:"RESEARCH / AI",DATA_SCIENCE:"DATA SCIENCE",PRODUCT_MANAGEMENT:"PRODUCT MANAGEMENT",UNKNOWN:"UNKNOWN"};

function money(job: Job) {
  if (!job.salary_min && !job.salary_max) return "Compensation not listed";
  const currency = job.salary_currency ?? "USD";
  const format = (value: number) => new Intl.NumberFormat("en-US", {style:"currency",currency,maximumFractionDigits:0,notation:"compact"}).format(value);
  return [job.salary_min, job.salary_max].filter(Boolean).map(value => format(value!)).join(" – ");
}

function JobCard({job}:{job:Job}) {
  const strengths = job.strengths.length ? job.strengths.slice(0,3) : job.matched_skills.length ? job.matched_skills.slice(0,3) : ["Awaiting score"];
  const gaps = job.gaps.length ? job.gaps.slice(0,2) : job.missing_skills.slice(0,2);
  return <Link href={`/jobs/${job.id}`} className="job-card">
    <div className="job-card-top"><div className="company-avatar">{job.company.slice(0,2).toUpperCase()}</div><div className="job-heading"><span>{job.company}</span><h2>{job.title}</h2><div className="family-line"><b className={`family-badge ${job.role_family.toLowerCase()}`}>{familyLabels[job.role_family]}</b>{job.career_transition_flag?<b className="transition-badge">TRANSITION</b>:null}</div></div><div className={`score score-${job.recommendation ?? "none"}`}><strong>{job.fit_score ?? "—"}</strong><span>FIT</span></div></div>
    <div className="job-meta"><span><MapPin size={14}/>{job.location ?? "Location not listed"}</span><span><BriefcaseBusiness size={14}/>{job.remote_type}</span><span>{money(job)}</span></div>
    <div className="fit-grid"><div><label>Top evidence</label><div className="chips">{strengths.map(item=><span className="positive" key={item}>{item}</span>)}</div></div><div><label>Watch areas</label><div className="chips">{gaps.length ? gaps.map(item=><span key={item}>{item}</span>) : <span>No critical gaps surfaced</span>}</div></div></div>
    <div className="job-context"><span>Source: {job.source}</span><span>Discovered {new Date(job.discovered_at).toLocaleDateString()}</span></div>
    <div className="job-footer"><div><span className={`recommendation ${job.recommendation ?? "unscored"}`}>Agent: {job.recommendation ?? "unscored"}</span>{job.human_label?<span className={`human-label ${job.human_label}`}>Nick: {job.human_label}</span>:null}</div><span>Open analysis <ArrowUpRight size={15}/></span></div>
  </Link>;
}

export default function Dashboard({data}:{data:JobList}) {
  const [filter,setFilter] = useState<(typeof filters)[number]>("all"); const [family,setFamily]=useState<(typeof families)[number]>("ALL");const [query,setQuery] = useState("");const [source,setSource]=useState("ALL");const [company,setCompany]=useState("ALL");const [location,setLocation]=useState("ALL");const [human,setHuman]=useState("ALL");
  const options=useMemo(()=>({sources:[...new Set(data.items.map(x=>x.source))],companies:[...new Set(data.items.map(x=>x.company))],locations:[...new Set(data.items.map(x=>x.normalized_location??x.location).filter(Boolean))]}),[data.items]);
  const jobs = useMemo(()=>data.items.filter(job => (filter === "all" || (filter === "skipped" ? job.application_status === "skipped" : job.recommendation === filter)) && (family==="ALL"||job.role_family===family)&&(source==="ALL"||job.source===source)&&(company==="ALL"||job.company===company)&&(location==="ALL"||(job.normalized_location??job.location)===location)&&(human==="ALL"||job.human_label===human)&& `${job.company} ${job.title} ${job.location}`.toLowerCase().includes(query.toLowerCase())),[data.items,filter,family,source,company,location,human,query]);
  const metrics = [{label:"Jobs scanned",value:data.counts.scanned,icon:Search},{label:"Passing filters",value:data.counts.passing_filters,icon:CircleCheck},{label:"Strong matches",value:data.counts.strong,icon:Command},{label:"Exceptional",value:data.counts.exceptional,icon:Sparkles},{label:"Ready for review",value:data.counts.ready,icon:BriefcaseBusiness}];
  return <div className="page-wrap">
    <header className="topbar"><div><p className="eyebrow">DISCOVERY CONTROL CENTER</p><h1>Job intelligence</h1><p>Evidence-led role discovery, filtering, and fit analysis.</p></div><div className="phase-badge"><span/> Phase 1 · Discovery</div></header>
    <section className="metric-grid" aria-label="Pipeline summary">{metrics.map(({label,value,icon:Icon})=><article key={label}><Icon size={17}/><span>{label}</span><strong>{value.toString().padStart(2,"0")}</strong></article>)}</section>
    <section className="family-tabs">{families.map(item=><button className={family===item?"active":""} key={item} onClick={()=>setFamily(item)}>{familyLabels[item]}</button>)}</section>
    <section className="toolbar"><div className="filter-tabs">{filters.map(item=><button className={filter===item?"active":""} key={item} onClick={()=>setFilter(item)}>{labels[item]}</button>)}</div><label className="search"><Search size={16}/><span className="sr-only">Search roles</span><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search roles"/></label></section>
    <section className="advanced-filters"><label>Source<select value={source} onChange={e=>setSource(e.target.value)}><option>ALL</option>{options.sources.map(x=><option key={x}>{x}</option>)}</select></label><label>Company<select value={company} onChange={e=>setCompany(e.target.value)}><option>ALL</option>{options.companies.map(x=><option key={x}>{x}</option>)}</select></label><label>Location<select value={location} onChange={e=>setLocation(e.target.value)}><option>ALL</option>{options.locations.map(x=><option key={x!}>{x}</option>)}</select></label><label>Nick&apos;s rating<select value={human} onChange={e=>setHuman(e.target.value)}><option>ALL</option><option>excellent</option><option>good</option><option>maybe</option><option>poor</option></select></label></section>
    <div className="section-heading"><div><h2>Role queue</h2><span>{jobs.length} results</span></div><p>Ranked by deterministic fit score</p></div>
    <section className="job-list">{jobs.length ? jobs.map(job=><JobCard key={job.id} job={job}/>) : <div className="empty-state"><div><Search size={24}/></div><h2>No roles in this view</h2><p>Scan a Greenhouse, Lever, or Ashby board through the API to populate the discovery queue.</p><code>POST /jobs/scan</code></div>}</section>
  </div>;
}
