import type { Metadata } from "next";
import Link from "next/link";
import { Radar, ShieldCheck } from "lucide-react";
import "./globals.css";
import "./phase2.css";
import "./phase25.css";

export const metadata: Metadata = { title: "Nick Job Agent", description: "Evidence-based AI job discovery and fit intelligence" };

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/"><span className="brand-mark"><Radar size={20}/></span><span>Nick<span> / Agent</span></span></Link>
        <nav aria-label="Main navigation"><Link href="/">Job intelligence</Link><Link href="/ingest">Add job URL</Link><Link href="/profile">Candidate memory</Link><Link href="/companies">Companies</Link><Link href="/sources">Sources</Link></nav>
        <div className="safety"><ShieldCheck size={18}/><div><strong>Truth boundary active</strong><p>Verified profile evidence only</p></div></div>
      </aside>
      <main>{children}</main>
    </div>
  </body></html>;
}
