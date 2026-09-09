import type { Metadata } from "next";
import Link from "next/link";
import { Radar, ShieldCheck } from "lucide-react";
import "./globals.css";
import "./phase2.css";
import "./phase25.css";
import "./phase4.css";
import "./mobile.css";

export const metadata: Metadata = { title: "RoleCall", description: "Automate the search. Not the ambition." };

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/"><span className="brand-mark"><Radar size={20}/></span><span>RoleCall</span></Link>
        <nav aria-label="Main navigation"><Link href="/">Home</Link><Link href="/dashboard">Opportunities</Link><Link href="/saved">Pipeline</Link><Link href="/market">Insights</Link><Link href="/profile">Profile</Link></nav>
        <div className="safety"><ShieldCheck size={18}/><div><strong>Local-first</strong><p>Verified evidence stays configurable</p></div></div>
      </aside>
      <main>{children}</main>
    </div>
  </body></html>;
}
