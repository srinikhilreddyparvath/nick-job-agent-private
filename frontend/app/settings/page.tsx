"use client";
import {useState} from "react";
import {useRouter} from "next/navigation";
import {apiFetch} from "@/lib/client-api";

export default function SettingsPage(){
 const router=useRouter();const [confirmation,setConfirmation]=useState("");const [status,setStatus]=useState("");const [busy,setBusy]=useState(false);
 async function reset(){setBusy(true);setStatus("Resetting generated local state...");try{const response=await apiFetch("/operations/reset-local-state",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmation})});const body=await response.json();if(!response.ok)throw new Error(body.detail??"Reset failed");window.localStorage.clear();window.sessionStorage.clear();setStatus("RoleCall was reset. Redirecting to onboarding...");router.push("/onboarding");router.refresh()}catch(error){setStatus(error instanceof Error?error.message:"Reset failed")}finally{setBusy(false)}}
 return <div className="page-wrap"><header className="topbar"><div><p className="eyebrow">LOCAL SETTINGS</p><h1>RoleCall settings</h1><p>Your profile, discovery results, and application artifacts stay in this local installation.</p></div></header><section className="panel danger-zone"><p className="panel-label">START FRESH</p><h2>Reset RoleCall</h2><p>This removes the candidate profile, uploaded resumes, preferences, sources, jobs, analyses, saved states, and generated artifacts. It preserves source code, examples, Docker configuration, environment variables, and API keys.</p><label>Type <b>RESET ROLECALL</b> to confirm<input value={confirmation} onChange={event=>setConfirmation(event.target.value)} /></label><button type="button" disabled={busy||confirmation!=="RESET ROLECALL"} onClick={reset}>{busy?"RESETTING...":"RESET LOCAL USER STATE"}</button>{status?<p role="status">{status}</p>:null}</section></div>
}
