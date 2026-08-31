import SourceManager from "@/components/SourceManager";
import {getScans,getSources} from "@/lib/api";
export default async function SourcesPage(){const [sources,scans]=await Promise.all([getSources(),getScans()]);return <div className="page-wrap"><header className="topbar"><div><p className="eyebrow">DISCOVERY INFRASTRUCTURE</p><h1>Sources</h1><p>Persistent ATS boards and observable scan history.</p></div></header><SourceManager sources={sources} scans={scans}/></div>}
