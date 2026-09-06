"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiError, apiFetch } from "@/lib/client-api";

export default function JobActions({jobId,status}:{jobId:number;status:string|null}) {
  const router=useRouter(); const [busy,setBusy]=useState(false); const [message,setMessage]=useState("");
  async function update(action:"shortlist"|"skip") { setBusy(true); setMessage(""); try { const response=await apiFetch(`/jobs/${jobId}/${action}`,{method:"POST"}); if(!response.ok) throw apiError(response,(await response.json().catch(()=>null))?.detail); setMessage(action==="shortlist"?"Added to shortlist":"Marked as skipped"); router.refresh(); } catch(error) { setMessage(error instanceof Error?error.message:"API request failed"); } finally { setBusy(false); } }
  return <div className="actions"><button disabled={busy} className="primary-action" onClick={()=>update("shortlist")}>SHORTLIST</button><button disabled={busy} onClick={()=>update("skip")}>SKIP</button>{message&&<p role="status">{message}</p>}<span>Current status: {status ?? "discovered"}</span></div>;
}
