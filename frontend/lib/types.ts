export type Recommendation = "exceptional" | "strong" | "possible" | "weak" | "skip";

export interface Job {
  id: number; external_id: string; source: string; company: string; title: string; location: string | null;
  remote_type: string; employment_type: string | null; salary_min: number | null; salary_max: number | null;
  salary_currency: string | null; description: string; requirements: string[]; preferred_qualifications: string[];
  apply_url: string; source_url: string; posted_at: string | null; discovered_at: string;
  fit_score: number | null; fit_explanation: string | null; matched_skills: string[]; missing_skills: string[];
  recommendation: Recommendation | null; application_status: string | null;
  component_scores: Record<string,{score:number;weight:number;explanation:string}>; strengths: string[]; gaps: string[];
  human_label: "excellent"|"good"|"maybe"|"poor"|null; human_notes:string|null;
  role_family:"RESEARCH_AI"|"DATA_SCIENCE"|"PRODUCT_MANAGEMENT"|"UNKNOWN";role_family_confidence:number;role_family_reasons:string[];classification_method:string;family_fit_score:number|null;family_component_scores:Record<string,{score:number;weight:number;explanation:string}>;matched_evidence_ids:string[];career_transition_flag:boolean;career_transition_notes:string|null;raw_company:string|null;canonical_company:string|null;normalized_location:string|null;alternate_sources:{source:string;source_url:string}[];
}

export interface JobList { items: Job[]; total: number; counts: {scanned:number; passing_filters:number; strong:number; exceptional:number; ready:number} }
export interface EvidenceRecord {id:string;category:string;sub_category:string;statement:string;source:string;source_reference:string;company:string|null;role:string|null;skills:string[];domains:string[];verified:boolean;confidence:number}
export interface ProfileItem {value:string;details:Record<string,string>;evidence_ids:string[]}
export interface CandidateProfile {identity:{name:string;legal_name:string;email:string;phone:string;location:string;evidence_ids:string[]};professional_summary:ProfileItem;roles:ProfileItem[];experience:ProfileItem[];education:ProfileItem[];skills:ProfileItem[];research:ProfileItem[];publications:ProfileItem[];patents:ProfileItem[];projects:ProfileItem[];technical_domains:ProfileItem[];leadership:ProfileItem[];portfolio_url:string;linkedin_url:string}
export interface JobSource {id:number;company:string;ats_type:string;board_identifier:string;careers_url:string|null;enabled:boolean;scan_frequency:string;last_scanned_at:string|null;last_success_at:string|null;last_error:string|null;jobs_discovered_total:number;created_at:string;updated_at:string}
export interface ScanRun {id:number;started_at:string;completed_at:string|null;status:string;source_count:number;successful_source_count:number;failed_source_count:number;jobs_fetched:number;jobs_filtered:number;jobs_deduplicated:number;jobs_added:number;jobs_updated:number;jobs_scored:number;exceptional_count:number;strong_count:number;possible_count:number;weak_count:number;skip_count:number;errors_json:{company?:string;error:string}[];duration_seconds:number|null}
export interface Company {id:number;name:string;canonical_name:string;website_url:string|null;careers_url:string|null;company_type:string;priority:string;enabled:boolean;notes:string|null;detected_ats:string|null;created_at:string;updated_at:string;source_count:number;last_scan:string|null}
