import Link from "next/link";
import {getProfile,getProfilePreferences} from "@/lib/server-api";

const detail=(item:{details:Record<string,string>})=>[item.details.role,item.details.start_date&&item.details.end_date?`${item.details.start_date} – ${item.details.end_date}`:item.details.start_date||item.details.end_date,item.details.location].filter(Boolean).join(" · ");

export default async function ProfilePage(){
 const [profile,preferences]=await Promise.all([getProfile(),getProfilePreferences()]);
 if(!profile||(!profile.identity.name&&!profile.experience.length&&!profile.skills.length))return <div className="page-wrap"><div className="empty-state"><h1>No candidate profile yet</h1><p>Upload a résumé, review the extracted details, and approve your profile to get started.</p><Link className="cta" href="/onboarding">GET STARTED</Link></div></div>;
 const research=[...profile.research,...profile.publications,...profile.patents];
 return <div className="page-wrap memory-page"><header className="topbar"><div><p className="eyebrow">YOUR CAREER PROFILE</p><h1>Profile</h1><p>The experience and preferences RoleCall uses to rank opportunities and prepare grounded materials.</p><Link className="cta compact" href="/onboarding">EDIT PROFILE</Link></div></header><div className="memory-content">
  <section className="panel"><p className="panel-label">SUMMARY</p><h2>{profile.identity.name||"Your professional profile"}</h2><p>{profile.professional_summary?.value||"Add a professional summary to sharpen your opportunity recommendations."}</p></section>
  <section className="panel"><p className="panel-label">EXPERIENCE</p><h2>Work experience</h2>{profile.experience.length?profile.experience.map(item=><article className="memory-employer" key={item.value}><h3>{item.value}</h3>{detail(item)?<p>{detail(item)}</p>:null}</article>):<p className="empty-copy">No work experience is listed yet.</p>}</section>
  <section className="panel"><p className="panel-label">SKILLS</p><h2>Skills and strengths</h2><div className="chips memory-chips">{profile.skills.map(item=><span key={item.value}>{item.value}</span>)}</div></section>
  <section className="panel"><p className="panel-label">EDUCATION</p><h2>Education</h2>{profile.education.length?profile.education.map(item=><article className="memory-item" key={item.value}><div><h3>{item.value}</h3>{detail(item)?<p>{detail(item)}</p>:null}</div></article>):<p className="empty-copy">No education is listed yet.</p>}</section>
  {profile.projects.length?<section className="panel"><p className="panel-label">PROJECTS</p><h2>Projects</h2>{profile.projects.map(item=><article className="memory-item" key={item.value}><div><h3>{item.value}</h3>{detail(item)?<p>{detail(item)}</p>:null}</div></article>)}</section>:null}
  {research.length?<section className="panel"><p className="panel-label">RESEARCH &amp; CREDENTIALS</p><h2>Research, publications, and certifications</h2>{research.map(item=><article className="memory-item" key={item.value}><div><h3>{item.value}</h3>{detail(item)?<p>{detail(item)}</p>:null}</div></article>)}</section>:null}
  <section className="panel"><p className="panel-label">PREFERENCES</p><h2>What you want next</h2><div className="chips memory-chips">{[...preferences.preferred_titles,...preferences.preferred_domains,...preferences.locations].map(value=><span key={value}>{value}</span>)}</div></section>
  <section className="panel"><p className="panel-label">CONSTRAINTS</p><h2>Working preferences</h2><p>{[preferences.remote_allowed&&"Remote",preferences.hybrid_allowed&&"Hybrid",preferences.onsite_allowed&&"On-site"].filter(Boolean).join(" · ")||"No workplace mode selected"}</p><p>{preferences.minimum_salary?`Minimum salary: ${preferences.minimum_salary.toLocaleString()}`:"No hard salary minimum set"}</p></section>
 </div></div>
}
