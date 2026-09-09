import "server-only";
import {connection} from "next/server";
import {AgentRun,ApplicationForm,ApplicationPackage,ApplicationSettings,ApplicationSummary,CandidateProfile,CareerRun,Company,ContactList,EvidenceRecord,EligibilityDecision,Job,JobList,JobResearchReport,JobSource,MorningReport,OperationsStatus,ScanRun,SemanticFitReport} from "@/lib/types";

const INTERNAL_API_URL=process.env.INTERNAL_API_URL??process.env.NEXT_PUBLIC_API_URL??"http://localhost:8000";

async function serverGet<T>(path:string,{optional=false}:{optional?:boolean}={}):Promise<T|null>{
 await connection();
 let response:Response;
 try{response=await fetch(`${INTERNAL_API_URL}${path}`,{cache:"no-store"})}
 catch{throw new Error(`Backend API unavailable at ${INTERNAL_API_URL}`)}
 if(optional&&response.status===404)return null;
 if(!response.ok)throw new Error(`Backend ${path} returned ${response.status}`);
 return response.json() as Promise<T>;
}

export const getJobs=()=>serverGet<JobList>("/jobs") as Promise<JobList>;
export const getJob=(id:string)=>serverGet<Job>(`/jobs/${id}`,{optional:true});
export const getProfile=()=>serverGet<CandidateProfile>("/profile");
export type ProfilePreferences={preferred_titles:string[];preferred_domains:string[];locations:string[];remote_allowed:boolean;hybrid_allowed:boolean;onsite_allowed:boolean;minimum_salary:number|null};
export const getProfilePreferences=async()=>((await serverGet<{preferences:ProfilePreferences}>("/onboarding")) as {preferences:ProfilePreferences}).preferences;
export const getEvidence=()=>serverGet<EvidenceRecord[]>("/profile/evidence") as Promise<EvidenceRecord[]>;
export const getSources=()=>serverGet<JobSource[]>("/sources") as Promise<JobSource[]>;
export const getScans=()=>serverGet<ScanRun[]>("/scans") as Promise<ScanRun[]>;
export const getCompanies=()=>serverGet<Company[]>("/companies") as Promise<Company[]>;
export const getAnalysis=(id:string)=>serverGet<SemanticFitReport>(`/jobs/${id}/analysis`,{optional:true});
export const getResearch=(id:string)=>serverGet<JobResearchReport>(`/jobs/${id}/research`,{optional:true});
export const getAgentRuns=(id:string)=>serverGet<AgentRun[]>(`/jobs/${id}/agent-runs`) as Promise<AgentRun[]>;
export const getApplicationPackage=(id:string)=>serverGet<ApplicationPackage>(`/jobs/${id}/application-package`,{optional:true});
export const getApplicationForm=(id:string)=>serverGet<ApplicationForm>(`/jobs/${id}/application-form`,{optional:true});
export const getEligibility=(id:string)=>serverGet<EligibilityDecision>(`/jobs/${id}/application-eligibility`,{optional:true});
export const getApplicationSettings=()=>serverGet<ApplicationSettings>("/application-settings");
export const getApplicationSummary=()=>serverGet<ApplicationSummary>("/application-summary");
export const getMorningReport=()=>serverGet<MorningReport>("/reports/morning/latest",{optional:true});
export const getOperationsStatus=()=>serverGet<OperationsStatus>("/operations/status",{optional:true});
export const getLatestCareerRun=()=>serverGet<CareerRun>("/career-intelligence/runs/latest",{optional:true});
export const getOnboardingState=()=>serverGet<{configured:boolean}>("/onboarding") as Promise<{configured:boolean}>;
export const getContacts=(id:string)=>serverGet<ContactList>(`/jobs/${id}/contacts`) as Promise<ContactList>;
