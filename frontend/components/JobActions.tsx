"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiError, apiFetch } from "@/lib/client-api";

export default function JobActions({jobId,status}:{jobId:number;status:string|null}) {
  const router=useRouter(); const [busy,setBusy]=useState(false); const [message,setMessage]=useState("");
  async function update(action:string) { setBusy(true); setMessage(""); try { const path=action==="shortlist"||action==="skip"?`/jobs/${jobId}/${action}`:`/jobs/${jobId}/status/${action}`;const response=await apiFetch(path,{method:"POST"}); if(!response.ok) throw apiError(response,(await response.json().catch(()=>null))?.detail); setMessage("Pipeline updated"); router.refresh(); } catch(error) { setMessage(error instanceof Error?error.message:"API request failed"); } finally { setBusy(false); } }
  return <div className="actions"><button disabled={busy} className="primary-action" onClick={()=>update("shortlist")}>SAVE</button><select aria-label="Pipeline status" disabled={busy} value={status??"discovered"} onChange={event=>update(event.target.value)}><option value="discovered" disabled>Discovered</option><option value="shortlisted">Saved</option><option value="applied">Applied</option><option value="interview">Interview</option><option value="offer">Offer</option><option value="hired">Hired</option><option value="rejected">Rejected</option><option value="no_response">No response</option><option value="withdrawn">Withdrawn</option></select><button disabled={busy} onClick={()=>update("skip")}>SKIP</button>{message&&<p role="status">{message}</p>}<span>Current status: {(status??"discovered").replaceAll("_"," ")}</span></div>;
}
