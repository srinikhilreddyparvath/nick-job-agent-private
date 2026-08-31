"use client";
import {FormEvent,useState,useTransition} from "react";
import {useRouter} from "next/navigation";
import {API_URL} from "@/lib/api";
const labels=["excellent","good","maybe","poor"] as const;
export default function JobFeedback({jobId,initialLabel,initialNotes,initialFamily}:{jobId:number;initialLabel:string|null;initialNotes:string|null;initialFamily:string}){
 const router=useRouter();const [pending,startTransition]=useTransition();const [label,setLabel]=useState(initialLabel??"");const [notes,setNotes]=useState(initialNotes??"");const [family,setFamily]=useState(initialFamily);const [status,setStatus]=useState("");
 async function save(event:FormEvent){event.preventDefault();if(!label)return;setStatus("Saving…");const response=await fetch(`${API_URL}/jobs/${jobId}/feedback`,{method:initialLabel?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({human_label:label,human_notes:notes||null,human_role_family:family})});setStatus(response.ok?"Assessment saved":"Could not save assessment");if(response.ok)startTransition(()=>router.refresh())}
 return <form className="feedback-panel panel" onSubmit={save}><p className="panel-label">NICK&apos;S ASSESSMENT</p><h2>Manual job-fit label</h2><div className="rating-options">{labels.map(item=><button type="button" className={label===item?`selected ${item}`:""} onClick={()=>setLabel(item)} key={item}>{item.toUpperCase()}</button>)}</div><label>Role family correction<select value={family} onChange={event=>setFamily(event.target.value)}><option>RESEARCH_AI</option><option>DATA_SCIENCE</option><option>PRODUCT_MANAGEMENT</option><option>UNKNOWN</option></select></label><label>Notes<textarea value={notes} onChange={event=>setNotes(event.target.value)} placeholder="What feels strong, unclear, or off?"/></label><div><button className="save-feedback" disabled={!label||pending} type="submit">SAVE ASSESSMENT</button><span role="status">{status}</span></div></form>
}
