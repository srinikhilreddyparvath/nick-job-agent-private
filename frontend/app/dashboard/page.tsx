import Dashboard from "@/components/Dashboard";
import Link from "next/link";
import {getJobs,getLatestCareerRun,getOnboardingState,getSources} from "@/lib/server-api";
export default async function DashboardPage(){const [data,sources,latestRun,onboarding]=await Promise.all([getJobs(),getSources(),getLatestCareerRun(),getOnboardingState()]);if(!onboarding.configured)return <div className="page-wrap"><section className="empty-state"><h1>Set up your career profile first</h1><p>Upload a resume, review the extracted evidence, and choose what you want from your next role.</p><Link className="cta" href="/onboarding">GET STARTED</Link></section></div>;return <Dashboard data={data} sources={sources} latestRun={latestRun} referenceDate={new Date().toISOString().slice(0,10)}/>}
