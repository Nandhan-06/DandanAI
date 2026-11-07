"use client";
import Link from "next/link";
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, Empty, ErrorBox, Label, Page, Select, Textarea, useLoad, Status } from "@/components/ui";
import { CitationCard } from "@/components/Citation";

export default function Criminal() {
  const { user, toast } = useAuth(); const cases = useLoad<any[]>("/api/v1/cases"); const [cid, setCid] = useState(""); const [inc, setInc] = useState(""); const [persp, setPersp] = useState("neutral"); const [busy, setBusy] = useState(false); const [rep, setRep] = useState<any>(null); const [run, setRun] = useState<any>(null); const [err, setErr] = useState<any>(null);
  const id = cid || cases.data?.find((c) => c.case_type === "criminal")?.id || cases.data?.[0]?.id;
  const go = async () => { setBusy(true); setErr(null); setRep(null); try { const r = await api(`/api/v1/cases/${id}/workflows/criminal`, { body: { incident: inc, perspective: persp } }); setRun(r); if (r.report_id) setRep(await api(`/api/v1/reports/${r.report_id}`)); else setErr(new Error(r.error || "Workflow failed")); } catch (e) { setErr(e); } setBusy(false); };
  const c = rep?.content;
  return (
    <Page title="DandanAI — Criminal intelligence" subtitle="Candidate offences, element mapping, evidence gaps, similar/contrary judgments — with citation verification. Never predicts guilt or outcome.">
      <div role="note" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"><ShieldAlert className="mr-1 inline h-4 w-4" />Candidate provisions are NOT verified law until supported by authoritative, human-verified sources. This tool assists legal professionals and does not replace judicial or legal decision-making.</div>
      {user.role !== "advocate" ? <Card><p className="text-sm text-ink-500">Only advocates can run criminal intelligence workflows.</p></Card> : !cases.data?.length ? <Card><Empty title="Create a case first">Reports attach to a case.</Empty></Card> :
        <Card title="Incident description"><div className="grid gap-3 sm:grid-cols-3"><div><Label htmlFor="c">Case</Label><Select id="c" value={id} onChange={(e: any) => setCid(e.target.value)}>{cases.data.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</Select></div><div><Label htmlFor="p">Perspective</Label><Select id="p" value={persp} onChange={(e: any) => setPersp(e.target.value)}><option value="neutral">Neutral</option><option value="prosecution">Prosecution</option><option value="defence">Defence</option></Select></div></div>
          <Label htmlFor="i">Describe the incident (facts only; min 20 characters)</Label><Textarea id="i" className="min-h-[140px]" value={inc} onChange={(e: any) => setInc(e.target.value)} placeholder="On 14 March 2024 near Central Market, an unknown person snatched my phone worth Rs. 18,000…" /><div className="mt-2"><Button onClick={go} loading={busy} disabled={inc.length < 20}>Run DandanAI analysis</Button></div></Card>}
      <ErrorBox error={err} />
      {rep && c && <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2"><Status s={rep.status} /><Badge tone="amber">{rep.mode} mode</Badge><Badge>citations: {c.citation_report.status.replaceAll("_", " ")}</Badge><Link className="text-sm text-brand-600 underline" href={`/reports/${rep.id}`}>Open full report / approve</Link>{run && <Link className="text-sm text-brand-600 underline" href={`/workflows?run=${run.id}`}>Agent monitor</Link>}</div>
        {c.incident.facts_to_confirm.length > 0 && <Card title="Facts to confirm">{c.incident.facts_to_confirm.map((f: string) => <div key={f} className="text-sm">• {f}</div>)}</Card>}
        {!c.statutes.mapped.length && <Card><Empty title="No candidate offence identified">The description did not match any offence indicators.</Empty></Card>}
        {c.statutes.mapped.map((m: any) => { const ev = c.evidence_plan.per_offence.find((e: any) => e.offence_key === m.offence_key); const pr = c.precedents.per_offence.find((e: any) => e.offence_key === m.offence_key); const pu = c.punishment.per_offence.find((e: any) => e.offence_key === m.offence_key);
          return <Card key={m.offence_key} title={m.label} actions={<Badge tone="amber">{m.verification_status.replaceAll("_", " ")}</Badge>}><p className="mb-2 text-xs text-ink-500">{m.reference_candidate}</p>
            <h3 className="text-sm font-semibold">Statutory elements</h3><div className="mb-3 flex flex-wrap gap-2">{m.element_mapping.map((e: any) => <Badge key={e.element} tone={e.status === "facts_present" ? "green" : e.status === "not_evident" ? "red" : "gray"}>{e.element}: {e.status.replace("_", " ")}</Badge>)}</div>
            {m.supporting_provisions.map((p: any) => <div key={p.chunk_id} className="mb-2"><CitationCard c={p} /></div>)}
            <h3 className="mt-3 text-sm font-semibold">Evidence checklist</h3><ul className="mb-3 text-sm">{ev?.checklist.map((x: any) => <li key={x.item}>{x.status === "gap" ? "☐" : "☑"} {x.item} {x.status === "gap" && <Badge tone="amber">gap</Badge>}</li>)}</ul>
            <div className="grid gap-3 lg:grid-cols-2"><div><h3 className="text-sm font-semibold">Similar judgments</h3>{pr?.similar.length ? pr.similar.map((x: any) => <div key={x.chunk_id} className="mb-2"><CitationCard c={x} /></div>) : <p className="text-sm text-ink-500">None retrieved.</p>}</div><div><h3 className="text-sm font-semibold">Contrary judgments</h3>{pr?.contrary.length ? pr.contrary.map((x: any) => <div key={x.chunk_id} className="mb-2"><CitationCard c={x} /></div>) : <p className="text-sm text-ink-500">None retrieved{c.precedents.perspective === "neutral" ? " (choose prosecution or defence perspective to isolate contrary authority)" : ""}.</p>}</div></div>
            <h3 className="mt-3 text-sm font-semibold">Punishment (from cited source only)</h3>{pu?.statutory_punishment.length ? pu.statutory_punishment.map((s: any, i: number) => <p key={i} className="text-sm">{s.statement}</p>) : <p className="text-sm text-amber-800">{pu?.status}</p>}</Card>; })}
        {c.punishment.victim_compensation.length > 0 && <Card title="Victim compensation sources">{c.punishment.victim_compensation.map((x: any) => <div key={x.chunk_id} className="mb-2"><CitationCard c={x} /></div>)}</Card>}
      </div>}
    </Page>
  );
}
