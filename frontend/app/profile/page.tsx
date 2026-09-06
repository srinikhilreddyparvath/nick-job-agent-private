import Link from "next/link";
import {BookOpen,Database,ShieldCheck} from "lucide-react";
import {getEvidence,getProfile} from "@/lib/server-api";

export default async function CandidateMemory(){
 const [profile,evidence]=await Promise.all([getProfile(),getEvidence()]);
 if(!profile||(!profile.identity.name&&!profile.experience.length&&!evidence.length))return <div className="page-wrap"><div className="empty-state"><h1>No candidate profile yet</h1><p>Upload a resume and approve the extracted evidence to create your local candidate memory.</p><Link className="cta" href="/onboarding">GET STARTED</Link></div></div>;
 const grouped=Object.groupBy(evidence,item=>item.company??item.category);
 return <div className="page-wrap memory-page"><header className="topbar"><div><p className="eyebrow">VERIFIED CANDIDATE STATE</p><h1>Candidate memory</h1><p>Traceable facts approved for matching and application preparation.</p><Link className="cta compact" href="/onboarding">EDIT PROFILE</Link></div><div className="memory-count"><Database size={17}/><strong>{evidence.length}</strong><span>evidence records</span></div></header>
 <section className="memory-identity"><div><span>PROFESSIONAL IDENTITY</span><h2>{profile.identity.name}</h2><p>Legal name: {profile.identity.legal_name}</p><p>{profile.identity.email} · {profile.identity.phone}</p></div><ShieldCheck size={28}/></section>
 <div className="memory-grid"><aside className="memory-index"><p className="panel-label">MEMORY INDEX</p><a href="#areas">Research areas</a><a href="#experience">Experience</a><a href="#research">Research & patents</a><a href="#education">Education</a><a href="#skills">Skills</a></aside><div className="memory-content">
 <section id="areas" className="panel"><p className="panel-label">TECHNICAL DOMAINS</p><h2>Research areas</h2><div className="chips memory-chips">{profile.technical_domains.map(x=><span key={x.value}>{x.value}</span>)}</div></section>
 <section id="experience" className="panel"><p className="panel-label">EXPERIENCE MEMORY</p><h2>Evidence by employer</h2>{profile.experience.map(exp=><article className="memory-employer" key={exp.value}><div><h3>{exp.value}</h3><p>{exp.details.role}</p></div><div>{exp.evidence_ids.map(id=><span key={id}>{id}</span>)}</div>{(grouped[exp.value]??[]).map(item=><p className="memory-statement" key={item.id}><b>{item.id}</b>{item.statement}</p>)}</article>)}</section>
 <section id="research" className="panel"><p className="panel-label">RESEARCH / IP</p><h2>Research and patents</h2>{[...profile.research,...profile.patents].map(item=><article className="memory-item" key={item.value}><BookOpen size={16}/><div><h3>{item.value}</h3><p>{item.details.type??item.details.status}</p><small>{item.evidence_ids.join(" · ")}</small></div></article>)}</section>
 <section id="education" className="panel"><p className="panel-label">EDUCATION</p>{profile.education.map(x=><article className="memory-item" key={x.value}><div><h3>{x.value}</h3><p>{x.details.institution} · {x.details.location}</p><small>{x.evidence_ids.join(" · ")}</small></div></article>)}</section>
 <section id="skills" className="panel"><p className="panel-label">VERIFIED SKILLS</p><div className="chips memory-chips">{profile.skills.map(x=><span key={x.value}>{x.value}<small>{x.evidence_ids[0]}</small></span>)}</div></section>
 </div></div></div>
}
