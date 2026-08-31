import Dashboard from "@/components/Dashboard";
import { getJobs } from "@/lib/api";

export default async function Home() { return <Dashboard data={await getJobs()}/>; }

