"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LayoutDashboard, Briefcase, FileText, Scale, MessageSquare, Workflow, ShieldAlert, Library, Users, Settings, LogOut, Menu, X, AlertTriangle } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Badge, Spinner } from "./ui";

const NAV = [["/", "Dashboard", LayoutDashboard], ["/cases", "Cases", Briefcase], ["/documents", "Documents", FileText], ["/research", "Legal research", Scale], ["/chat", "AI chat", MessageSquare],
  ["/workflows", "Agent monitor", Workflow], ["/criminal", "DandanAI criminal", ShieldAlert], ["/sources", "Source coverage", Library], ["/admin", "Admin", Users, "admin"], ["/settings", "Settings", Settings]] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout, status } = useAuth(); const path = usePathname(); const router = useRouter(); const [open, setOpen] = useState(false);
  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);
  useEffect(() => setOpen(false), [path]);
  if (loading || !user) return <Spinner label="Checking session…" />;
  const mock = status?.mode?.overall !== "live"; const db = status?.database?.state;
  return (
    <div className="flex min-h-screen">
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-ink-900 text-ink-100 transition md:static md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`} aria-label="Primary">
        <div className="flex items-center justify-between px-5 py-4"><div><div className="font-serif text-xl font-semibold tracking-wide">DandanAI</div><div className="text-xs text-ink-200">Legal intelligence · DandanAI</div></div><button className="md:hidden" onClick={() => setOpen(false)} aria-label="Close menu"><X /></button></div>
        <nav className="space-y-0.5 px-2">{NAV.filter((n) => !n[3] || n[3] === user.role).map(([href, label, Icon]) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return <Link key={href} href={href} className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${active ? "bg-white/10 text-white" : "text-ink-200 hover:bg-white/5"}`} aria-current={active ? "page" : undefined}><Icon className="h-4 w-4" />{label}</Link>;
        })}</nav>
        <div className="absolute bottom-0 w-full border-t border-white/10 p-4 text-xs"><div className="truncate font-medium">{user.full_name}</div><div className="mb-2 text-ink-200">{user.role.replace("_", " ")}</div><button onClick={logout} className="flex items-center gap-2 text-ink-200 hover:text-white"><LogOut className="h-4 w-4" />Sign out</button></div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-ink-200 bg-white px-4 py-2"><button className="md:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu /></button>
          <div className="flex flex-wrap items-center gap-2 text-xs"><Badge tone={mock ? "amber" : "green"}>{mock ? "MOCK MODE — no live AI" : "LIVE AI"}</Badge>
            <Badge tone={db === "CONNECTED" ? "green" : db === "EPHEMERAL_TEST_DB_NOT_NEON" ? "amber" : "red"}>{db === "CONNECTED" ? "Neon connected" : db === "EPHEMERAL_TEST_DB_NOT_NEON" ? "TEST DB (not Neon)" : db === "BLOCKED_NO_NEON_CREDENTIALS" ? "Neon not configured" : status?.unreachable ? "API unreachable" : "DB error"}</Badge></div>
          <div className="ml-auto hidden text-xs text-ink-500 lg:block"><AlertTriangle className="mr-1 inline h-3 w-3" />Decision support only — not legal advice</div></header>
        <main className="min-w-0 flex-1">{db === "BLOCKED_NO_NEON_CREDENTIALS" && <div role="alert" className="m-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">The database is not configured. Add your Neon <code>DATABASE_URL</code> / <code>DIRECT_URL</code> to <code>.env</code>, run <code>alembic upgrade head</code>, and restart the backend.</div>}{children}</main>
      </div>
    </div>
  );
}
