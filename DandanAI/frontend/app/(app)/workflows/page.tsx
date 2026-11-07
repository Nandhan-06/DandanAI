"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Check, X, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, Empty, ErrorBox, Page, Spinner, Status, Table, Td, Textarea, useLoad } from "@/components/ui";

const ORDER = ["document_analysis", "legal_research", "case_assessment", "adversarial_review", "citation_verification", "human_review_gate"];
const CRIM = ["incident_analysis", "crime_classification", "statute_mapping", "evidence_planner", "precedent_research", "punishment_compensation", "citation_verification", "human_review_gate"];

function Monitor() {
  const sp = useSearchParams(); const runId = sp.get("run"); const { user, toast } = useAuth(); const runs = useLoad<any[]>("/api/v1/workflows"); const run = useLoad<any>(runId ? `/api/v1/workflows/${runId}` : null, [runId]); const [note, setNote] = useState("");
  const act = async (a: string) => { try { await api(`/api/v1/workflows/${runId}/${a}`, { body: a === "resume" ? undefined : { note }, method: "POST" }); toast(a === "resume" ? "Resumed from checkpoint" : `Report ${a}d`); run.reload(); runs.reload(); } catch (e: any) { toast(e.message, "err"); } };
  const r = run.data; const names = r?.kind === "criminal_intelligence" ? CRIM : ORDER;
  return (
    <Page title="Multi-agent execution monitor" subtitle="Typed state, explicit routing, retries, checkpoints and human approval">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Runs" className="lg:col-span-1">{runs.loading && !runs.data ? <Spinner /> : !runs.data?.length ? <Empty title="No runs yet">Start one from a case or DandanAI.</Empty> : runs.data.map((x) => <Link key={x.id} href={`/workflows?run=${x.id}`} className={`mb-1 flex items-center justify-between rounded px-2 py-1.5 text-sm ${runId === x.id ? "bg-brand-50" : "hover:bg-ink-50"}`}><span>{x.kind.replace("_", " ")}<div className="text-xs text-ink-500">{new Date(x.created_at).toLocaleString()}</div></span><Status s={x.status} /></Link>)}</Card>
        <div className="space-y-4 lg:col-span-2">{!runId ? <Card><Empty title="Select a run" /></Card> : run.loading && !r ? <Spinner /> : r && <>
          <ErrorBox error={run.error || (r.error && new Error(r.error))} />
          <Card title={`Run ${r.id.slice(0, 8)} — ${r.kind.replace("_", " ")}`} actions={<><Badge tone="amber">{r.mode}</Badge><Status s={r.status} /></>}>
            <div className="mb-4 flex flex-wrap items-center gap-1">{names.map((n, i) => { const steps = r.steps.filter((s: any) => s.agent === n); const last = steps[steps.length - 1]; const tone = !last ? "bg-ink-100 text-ink-500" : last.status === "ok" ? "bg-emerald-100 text-emerald-800" : last.status === "failed" ? "bg-red-100 text-red-800" : last.status === "retrying" ? "bg-amber-100 text-amber-900" : "bg-ink-100"; return <span key={n} className="flex items-center gap-1"><span className={`rounded px-2 py-1 text-xs ${tone}`}>{n.replaceAll("_", " ")}{steps.length > 1 && ` ×${steps.length}`}</span>{i < names.length - 1 && <span className="text-ink-200">→</span>}</span>; })}</div>
            <Table head={["#", "Agent", "Status", "Attempt", "ms", "Summary / error"]}>{r.steps.map((s: any) => <tr key={s.id}><Td>{s.seq}</Td><Td>{s.agent.replaceAll("_", " ")}</Td><Td><Status s={s.status} /></Td><Td>{s.attempt}</Td><Td>{s.duration_ms}</Td><Td className="text-xs">{s.error || s.summary}</Td></tr>)}</Table>
            <div className="mt-2 text-xs text-ink-500">Checkpoints persisted: {r.checkpoints.join(" → ") || "none"}</div></Card>
          {r.status === "failed" && user.role === "advocate" && <Button onClick={() => act("resume")}><RotateCcw className="h-4 w-4" />Resume from last checkpoint</Button>}
          {r.status === "awaiting_review" && <Card title="Human review required"><p className="mb-2 text-sm">A draft report was generated. An advocate must approve or reject it before it can be relied on.</p>{r.report_id && <Link className="text-sm text-brand-600 underline" href={`/reports/${r.report_id}`}>Open report</Link>}
            {user.role === "advocate" ? <div className="mt-2 space-y-2"><Textarea placeholder="Review note (optional)" value={note} onChange={(e: any) => setNote(e.target.value)} aria-label="Review note" /><div className="flex gap-2"><Button onClick={() => act("approve")}><Check className="h-4 w-4" />Approve</Button><Button variant="danger" onClick={() => act("reject")}><X className="h-4 w-4" />Reject</Button></div></div> : <p className="mt-2 text-sm text-ink-500">Only advocates can approve.</p>}</Card>}
        </>}</div></div>
    </Page>
  );
}
export default function Workflows() { return <Suspense fallback={<Spinner />}><Monitor /></Suspense>; }
