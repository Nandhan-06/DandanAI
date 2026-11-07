"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Archive } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, ErrorBox, Page, Spinner, Status, Tabs, useLoad, Badge, Input, Card } from "@/components/ui";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { Facts, Intelligence, Matrix, Overview, Timeline, Twin } from "@/components/CasePanels";

export default function CaseDetail() {
  const { id } = useParams<{ id: string }>(); const { toast, user } = useAuth(); const [tab, setTab] = useState("overview"); const c = useLoad<any>(`/api/v1/cases/${id}`); const mem = useLoad<any[]>(`/api/v1/cases/${id}/members`); const [email, setEmail] = useState("");
  if (c.loading && !c.data) return <Spinner />; if (c.error) return <div className="p-6"><ErrorBox error={c.error} /></div>; const d = c.data;
  const archive = async () => { await api(`/api/v1/cases/${id}/archive`, { method: "POST" }); toast("Case archived"); c.reload(); };
  const share = async () => { try { await api(`/api/v1/cases/${id}/members`, { body: { user_email: email, access: "editor" } }); setEmail(""); mem.reload(); toast("Shared"); } catch (e: any) { toast(e.message, "err"); } };
  return (
    <Page title={d.title} subtitle={`${d.case_type || "case"} · ${d.jurisdiction || "jurisdiction not set"} · your access: ${d.access}`} actions={<>{d.is_synthetic && <Badge tone="amber">synthetic</Badge>}<Status s={d.status} />{d.status === "open" && d.access !== "viewer" && <Button variant="outline" onClick={archive}><Archive className="h-4 w-4" />Archive</Button>}</>}>
      <Tabs value={tab} onChange={setTab} tabs={[["overview", "Overview"], ["documents", "Documents"], ["facts", "Facts & issues"], ["matrix", "Evidence matrix"], ["timeline", "Timeline"], ["twin", "Case Twin"], ["intel", "Intelligence & reports"], ["sharing", "Sharing"]]} />
      {tab === "overview" && <Overview caseId={id} />}{tab === "documents" && <DocumentsPanel caseId={id} />}{tab === "facts" && <Facts caseId={id} />}{tab === "matrix" && <Matrix caseId={id} />}{tab === "timeline" && <Timeline caseId={id} />}{tab === "twin" && <Twin caseId={id} />}{tab === "intel" && <Intelligence caseId={id} />}
      {tab === "sharing" && <Card title="Case access">{mem.data?.map((m) => <div key={m.user_id} className="text-sm">{m.full_name} ({m.email}) — {m.access}</div>)}{!mem.data?.length && <p className="text-sm text-ink-500">Only you can access this case.</p>}
        {d.is_owner !== false && user.role === "advocate" && d.access === "owner" && <div className="mt-3 flex gap-2"><Input placeholder="colleague@yourorg.com (same organisation)" value={email} onChange={(e: any) => setEmail(e.target.value)} aria-label="Colleague email" /><Button onClick={share}>Share (editor)</Button></div>}</Card>}
    </Page>
  );
}
