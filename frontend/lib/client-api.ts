import {API_URL} from "@/lib/api";

export type ApiErrorCode="NETWORK_FAILURE"|"APPLICATION_BLOCKED"|"VALIDATION_FAILED"|"SUBMISSION_FAILED"|"SUBMISSION_UNVERIFIED"|"CAPTCHA_REQUIRED"|"EXTERNAL_AUTH_REQUIRED"|"API_ERROR";

export class ApiClientError extends Error{
 constructor(public code:ApiErrorCode,message:string,public status?:number){super(message);this.name="ApiClientError"}
}

export async function apiFetch(path:string,init:RequestInit={}){
 const headers=new Headers(init.headers);
 try{return await fetch(`${API_URL}${path}`,{...init,headers})}
 catch{throw new ApiClientError("NETWORK_FAILURE","Network connection failed")}
}

export function apiError(response:Response,detail?:string){
 if(detail?.includes("SUBMISSION_UNVERIFIED"))return new ApiClientError("SUBMISSION_UNVERIFIED","Submission could not be verified",response.status);
 if(detail?.includes("CAPTCHA"))return new ApiClientError("CAPTCHA_REQUIRED","Application is blocked by CAPTCHA",response.status);
 if(detail?.includes("AUTH"))return new ApiClientError("EXTERNAL_AUTH_REQUIRED","The employer application requires external authentication",response.status);
 if(response.status===409)return new ApiClientError("APPLICATION_BLOCKED",detail||"Application action blocked",409);
 if(response.status===422)return new ApiClientError("VALIDATION_FAILED",detail||"Request validation failed",422);
 return new ApiClientError("API_ERROR",detail||`API request failed (${response.status})`,response.status);
}
