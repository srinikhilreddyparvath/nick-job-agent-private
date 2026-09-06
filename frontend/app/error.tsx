"use client";
export default function ErrorPage({error,reset}:{error:Error&{digest?:string};reset:()=>void}){
 return <main className="page-wrap"><section className="empty-state" role="alert"><h1>Unable to load job data</h1><p>{error.message||"The authenticated backend request failed. This is not an empty job queue."}</p><button type="button" onClick={reset}>TRY AGAIN</button></section></main>;
}
