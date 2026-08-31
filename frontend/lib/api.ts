import { CandidateProfile,Company,EvidenceRecord,Job,JobList,JobSource,ScanRun } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getJobs(): Promise<JobList> {
  try {
    const response = await fetch(`${API_URL}/jobs`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    return response.json();
  } catch {
    return { items: [], total: 0, counts: {scanned:0, passing_filters:0, strong:0, exceptional:0, ready:0} };
  }
}

export async function getJob(id: string): Promise<Job | null> {
  try {
    const response = await fetch(`${API_URL}/jobs/${id}`, { cache: "no-store" });
    return response.ok ? response.json() : null;
  } catch { return null; }
}

export { API_URL };

async function safeGet<T>(path:string,fallback:T):Promise<T>{try{const response=await fetch(`${API_URL}${path}`,{cache:"no-store"});if(!response.ok)throw new Error();return response.json()}catch{return fallback}}
export const getProfile=()=>safeGet<CandidateProfile|null>("/profile",null);
export const getEvidence=()=>safeGet<EvidenceRecord[]>("/profile/evidence",[]);
export const getSources=()=>safeGet<JobSource[]>("/sources",[]);
export const getScans=()=>safeGet<ScanRun[]>("/scans",[]);
export const getCompanies=()=>safeGet<Company[]>("/companies",[]);
