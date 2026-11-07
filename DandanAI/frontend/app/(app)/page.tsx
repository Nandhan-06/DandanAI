"use client";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Card, Empty, Page, Spinner, Status, Table, Td, useLoad, Badge } from "@/components/ui";

export default function Dashboard() {
  const { user, status } = useAuth(); const admin = user.role === "admin";
  const cases = useLoad<any[]>(admin ? null : "/api/v1/cases"); const runs = useLoad<any[]>(admin ? null : "/api/v1/workflows"); const reps = useLoad<any[]>(admin ? null : "/api/v1/reports"); const stats = useLoad<any>(admin ? "/api/v1/admin/stats" : null);
  const open = cases.data?.filter((c) => c.status === "open") || []; const draft = reps.data?.filter((r) => r.status === "draft") || [];
  const tiles = admin ? [["Users", stats.data?.users], ["Cases", stats.data?.cases], ["Documents", stats.data?.documents], ["Workflow runs", stats.data?.workflow_runs]] : [["Open cases", open.length], ["Agent runs", runs.data?.length], ["Reports awaiting review", draft.length], ["Total cases", cases.data?.length]];
  return (
    <Page title={`Welcome, ${user.full_name.split(" ")[0]}`} subtitle="DandanAI — national legal intelligence with the DandanAI criminal engine">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{tiles.map(([l, v]: any) => <Card key={l}><div className="text-3xl font-semibold">{v ?? "–"}</div><div className="text-xs text-ink-500">{l}</div></Card>)}</div>
      {status && <Card title="System transparency"><div className="flex flex-wrap gap-2 text-sm">{Object.entries(status.mode || {}).filter(([k]) => k !== "overall").map(([k, v]: any) => <Badge key={k} tone={v === "live" ? "green" : "amber"}>{k}: {v}</Badge>)}<Badge tone={status.database?.state === "CONNECTED" ? "green" : "amber"}>database: {String(status.database?.state).replaceAll("_", " ").toLowerCase()}</Badge></div><p className="mt-2 text-xs text-ink-500">{status.disclaimer}</p></Card>}
      {!admin && <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Recent cases">{cases.loading ? <Spinner /> : !cases.data?.length ? <Empty title="No cases yet"><Link className="text-brand-600 underline" href="/cases">Create a case</Link></Empty> : <Table head={["Case", "Type", "Status"]}>{cases.data.slice(0, 6).map((c) => <tr key={c.id}><Td><Link className="text-brand-600 hover:underline" href={`/cases/${c.id}`}>{c.title}</Link></Td><Td>{c.case_type}</Td><Td><Status s={c.status} /></Td></tr>)}</Table>}</Card>
        <Card title="Reports awaiting your review">{!draft.length ? <Empty title="Nothing pending" /> : draft.map((r) => <div key={r.id} className="mb-1 text-sm"><Link className="text-brand-600 underline" href={`/reports/${r.id}`}>{r.title}</Link> <Status s={r.status} /></div>)}</Card></div>}
    </Page>
  );
}
