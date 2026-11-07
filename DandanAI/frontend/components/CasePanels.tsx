"use client";
import { useState } from "react";
import { Plus, Trash2, Play, RefreshCw } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Select, Spinner, Status, Table, Td, Textarea, useLoad } from "./ui";

function useCrud(caseId: string, path: string) {
  const { toast } = useAuth(); const l = useLoad<any[]>(`/api/v1/cases/${caseId}/${path}`);
  const add = async (body: any) => { try { await api(`/api/v1/cases/${caseId}/${path}`, { body }); l.reload(); return true; } catch (e: any) { toast(e.message, "err"); return false; } };
  const del = async (id: string) => { try { await api(`/api/v1/cases/${caseId}/${path}/${id}`, { method: "DELETE" }); l.reload(); } catch (e: any) { toast(e.message, "err"); } };
  const patch = async (id: string, body: any) => { try { await api(`/api/v1/cases/${caseId}/${path}/${id}`, { method: "PATCH", body }); l.reload(); } catch (e: any) { toast(e.message, "err"); } };
  return { ...l, add, del, patch };
}

export function Overview({ caseId }: { caseId: string }) {
  const { data, error, loading } = useLoad<any>(`/api/v1/cases/${caseId}/cockpit`); const act = useLoad<any[]>(`/api/v1/cases/${caseId}/activity`);
  if (loading) return <Spinner />; if (error) return <ErrorBox error={error} />; const d = data!;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card title="Case Intelligence Cockpit" className="lg:col-span-2"><p className="text-sm">{d.case.description || <i>No description</i>}</p>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">{[["Documents", d.documents.total], ["Unprocessed", d.documents.unprocessed], ["Items to review", d.documents.pending_review_items], ["Issues w/o evidence", d.evidence.issues_without_evidence], ["Missing evidence", d.evidence.missing], ["Reports awaiting review", d.reports_awaiting_review]].map(([l, v]: any) => <div key={l} className="rounded-lg bg-ink-50 p-3"><div className="text-2xl font-semibold">{v}</div><div className="text-xs text-ink-500">{l}</div></div>)}</div></Card>
      <Card title="Deadline & limitation flags (advocate review)">{!d.alerts.length ? <Empty title="No flags" /> : d.alerts.map((a: any) => <div key={a.task_id} className="mb-2 text-sm"><Status s={a.flag || "needs review"} /> {a.title} <span className="text-ink-500">{a.due}</span>{a.needs_review && <Badge tone="amber">extracted – unreviewed</Badge>}</div>)}<p className="mt-2 text-xs text-ink-500">Limitation periods are never assumed; enter them as tasks.</p></Card>
      <Card title="Recent agent runs">{!d.recent_runs.length ? <Empty title="No runs" /> : d.recent_runs.map((r: any) => <div key={r.id} className="mb-1 text-sm"><Link className="text-brand-600 underline" href={`/workflows?run=${r.id}`}>{r.kind.replace("_", " ")}</Link> <Status s={r.status} /></div>)}</Card>
      <Card title="Activity history" className="lg:col-span-2">{!act.data?.length ? <Empty /> : <ul className="max-h-56 space-y-1 overflow-auto text-xs">{act.data.map((a, i) => <li key={i}><span className="text-ink-500">{new Date(a.at).toLocaleString()}</span> — {a.action}</li>)}</ul>}</Card>
    </div>
  );
}

export function Facts({ caseId }: { caseId: string }) {
  const parties = useCrud(caseId, "parties"), facts = useCrud(caseId, "facts"), issues = useCrud(caseId, "issues"), tasks = useCrud(caseId, "tasks");
  const [p, setP] = useState({ name: "", role: "" }), [f, setF] = useState({ text: "", disputed: false, fact_date: "" }), [i, setI] = useState({ title: "", description: "" }), [t, setT] = useState({ title: "", kind: "task", due_date: "", trigger_date: "", period_days: "" });
  const clean = (o: any) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== "" && v !== null).map(([k, v]) => [k, k === "period_days" ? Number(v) : v]));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Parties & relationships"><div className="mb-2 flex gap-2"><Input placeholder="Name" value={p.name} onChange={(e: any) => setP({ ...p, name: e.target.value })} aria-label="Party name" /><Input placeholder="Role (tenant, accused…)" value={p.role} onChange={(e: any) => setP({ ...p, role: e.target.value })} aria-label="Party role" /><Button onClick={async () => { if (p.name && p.role && await parties.add(p)) setP({ name: "", role: "" }); }} aria-label="Add party"><Plus className="h-4 w-4" /></Button></div>
        {!parties.data?.length ? <Empty /> : parties.data.map((x) => <div key={x.id} className="flex justify-between border-b py-1 text-sm"><span>{x.name} <Badge>{x.role}</Badge></span><button aria-label="Delete" onClick={() => parties.del(x.id)}><Trash2 className="h-4 w-4 text-ink-500" /></button></div>)}</Card>
      <Card title="Legal issues"><div className="mb-2 flex gap-2"><Input placeholder="Issue title" value={i.title} onChange={(e: any) => setI({ ...i, title: e.target.value })} aria-label="Issue title" /><Button onClick={async () => { if (i.title && await issues.add(clean(i))) setI({ title: "", description: "" }); }} aria-label="Add issue"><Plus className="h-4 w-4" /></Button></div>
        {!issues.data?.length ? <Empty /> : issues.data.map((x) => <div key={x.id} className="flex justify-between border-b py-1 text-sm"><span>{x.title}</span><button aria-label="Delete" onClick={() => issues.del(x.id)}><Trash2 className="h-4 w-4 text-ink-500" /></button></div>)}</Card>
      <Card title="Facts & disputed facts"><div className="mb-2 space-y-2"><Textarea placeholder="Fact" value={f.text} onChange={(e: any) => setF({ ...f, text: e.target.value })} aria-label="Fact text" /><div className="flex items-center gap-2"><Input type="date" className="!w-40" value={f.fact_date} onChange={(e: any) => setF({ ...f, fact_date: e.target.value })} aria-label="Fact date" /><label className="text-sm"><input type="checkbox" checked={f.disputed} onChange={(e) => setF({ ...f, disputed: e.target.checked })} /> disputed</label><Button onClick={async () => { if (f.text && await facts.add(clean(f))) setF({ text: "", disputed: false, fact_date: "" }); }}><Plus className="h-4 w-4" />Add</Button></div></div>
        {!facts.data?.length ? <Empty /> : facts.data.map((x) => <div key={x.id} className="flex justify-between border-b py-1 text-sm"><span>{x.text} {x.disputed && <Badge tone="amber">disputed</Badge>} <span className="text-xs text-ink-500">{x.fact_date}</span></span><button aria-label="Delete" onClick={() => facts.del(x.id)}><Trash2 className="h-4 w-4 text-ink-500" /></button></div>)}</Card>
      <Card title="Tasks, deadlines & limitation"><div className="mb-2 grid grid-cols-2 gap-2"><Input placeholder="Title" value={t.title} onChange={(e: any) => setT({ ...t, title: e.target.value })} aria-label="Task title" /><Select value={t.kind} onChange={(e: any) => setT({ ...t, kind: e.target.value })} aria-label="Kind"><option value="task">Task</option><option value="deadline">Deadline</option><option value="limitation">Limitation (enter trigger + period)</option></Select>
        {t.kind === "limitation" ? <><div><Label>Trigger date</Label><Input type="date" value={t.trigger_date} onChange={(e: any) => setT({ ...t, trigger_date: e.target.value })} /></div><div><Label>Period (days) — advocate to confirm</Label><Input type="number" value={t.period_days} onChange={(e: any) => setT({ ...t, period_days: e.target.value })} /></div></> : <Input type="date" value={t.due_date} onChange={(e: any) => setT({ ...t, due_date: e.target.value })} aria-label="Due date" />}
        <Button onClick={async () => { if (t.title && await tasks.add(clean(t))) setT({ title: "", kind: "task", due_date: "", trigger_date: "", period_days: "" }); }}><Plus className="h-4 w-4" />Add</Button></div>
        {!tasks.data?.length ? <Empty /> : tasks.data.map((x) => <div key={x.id} className="flex items-center justify-between border-b py-1 text-sm"><span className={x.done ? "line-through text-ink-500" : ""}>{x.title} <Badge>{x.kind}</Badge> {x.due_date} {!x.reviewed && <Badge tone="amber">unreviewed</Badge>}</span><span className="flex gap-1"><Button variant="outline" onClick={() => tasks.patch(x.id, { done: !x.done, reviewed: true })}>{x.done ? "Reopen" : "Done"}</Button><button aria-label="Delete" onClick={() => tasks.del(x.id)}><Trash2 className="h-4 w-4 text-ink-500" /></button></span></div>)}</Card>
    </div>
  );
}

export function Matrix({ caseId }: { caseId: string }) {
  const m = useLoad<any>(`/api/v1/cases/${caseId}/evidence-matrix`); const ev = useCrud(caseId, "evidence"); const [e, setE] = useState({ title: "", kind: "document", status: "held", supports: "supports", issue_ids: [] as string[] });
  if (m.loading && !m.data) return <Spinner />; const d = m.data; const reloadAll = () => { m.reload(); ev.reload(); };
  return (
    <div className="space-y-4">
      <Card title="Add evidence & map to issues"><div className="grid gap-2 sm:grid-cols-5"><Input placeholder="Evidence title" value={e.title} onChange={(x: any) => setE({ ...e, title: x.target.value })} aria-label="Evidence title" />
        <Select value={e.kind} onChange={(x: any) => setE({ ...e, kind: x.target.value })} aria-label="Evidence kind">{["document", "witness", "digital", "physical", "expert"].map((k) => <option key={k}>{k}</option>)}</Select>
        <Select value={e.status} onChange={(x: any) => setE({ ...e, status: x.target.value })} aria-label="Evidence status">{["held", "requested", "missing"].map((k) => <option key={k}>{k}</option>)}</Select>
        <Select value={e.supports} onChange={(x: any) => setE({ ...e, supports: x.target.value })} aria-label="Supports">{["supports", "undermines", "neutral"].map((k) => <option key={k}>{k}</option>)}</Select>
        <Button onClick={async () => { if (e.title && await ev.add(e)) { setE({ ...e, title: "" }); m.reload(); } }}><Plus className="h-4 w-4" />Add</Button></div>
        <div className="mt-2 flex flex-wrap gap-2 text-sm">{d?.issues.map((i: any) => <label key={i.id}><input type="checkbox" checked={e.issue_ids.includes(i.id)} onChange={(x) => setE({ ...e, issue_ids: x.target.checked ? [...e.issue_ids, i.id] : e.issue_ids.filter((y) => y !== i.id) })} /> {i.title}</label>)}{!d?.issues.length && <span className="text-ink-500">Add legal issues first to map evidence to arguments.</span>}</div></Card>
      <Card title="Evidence matrix (evidence × legal issue)" actions={<Button variant="ghost" onClick={reloadAll}><RefreshCw className="h-4 w-4" /></Button>}>
        {!d?.rows.length ? <Empty title="No evidence">Add evidence above.</Empty> : <Table head={["Evidence", "Status", ...d.issues.map((i: any) => i.title)]}>{d.rows.map((r: any) => <tr key={r.evidence_id}><Td>{r.title} <Badge>{r.kind}</Badge></Td><Td><Status s={r.status} /></Td>{d.issues.map((i: any) => <Td key={i.id}>{r.cells[i.id] ? <Badge tone={r.cells[i.id] === "supports" ? "green" : r.cells[i.id] === "undermines" ? "red" : "gray"}>{r.cells[i.id]}</Badge> : "–"}</Td>)}</tr>)}</Table>}
        {!!d?.issues_without_evidence.length && <div className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-900"><b>Gaps:</b> no evidence mapped to: {d.issues_without_evidence.map((g: any) => g.issue).join("; ")}</div>}</Card>
    </div>
  );
}

export function Timeline({ caseId }: { caseId: string }) {
  const tl = useCrud(caseId, "timeline"); const [e, setE] = useState({ title: "", event_date: "", description: "" });
  const rows = [...(tl.data || [])].sort((a, b) => (a.event_date || "9999").localeCompare(b.event_date || "9999"));
  return (
    <Card title="Case timeline"><div className="mb-3 flex flex-wrap gap-2"><Input type="date" className="!w-40" value={e.event_date} onChange={(x: any) => setE({ ...e, event_date: x.target.value })} aria-label="Event date" /><Input className="flex-1" placeholder="Event" value={e.title} onChange={(x: any) => setE({ ...e, title: x.target.value })} aria-label="Event title" /><Button onClick={async () => { if (e.title && await tl.add(Object.fromEntries(Object.entries(e).filter(([, v]) => v)))) setE({ title: "", event_date: "", description: "" }); }}><Plus className="h-4 w-4" />Add</Button></div>
      {tl.loading && !tl.data ? <Spinner /> : !rows.length ? <Empty title="No events">Dates found in uploaded documents appear here automatically.</Empty> :
        <ol className="relative ml-2 border-l-2 border-brand-100 pl-5">{rows.map((r) => <li key={r.id} className="mb-4"><span className="absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full bg-brand-500" /><div className="text-xs font-medium text-brand-700">{r.event_date || "undated"} {r.source === "extracted" && <Badge tone="amber">from document p.{r.page}</Badge>}</div><div className="text-sm font-medium">{r.title}</div>{r.description && <div className="text-xs text-ink-500">{r.description}</div>}<button className="text-xs text-ink-500 underline" onClick={() => tl.del(r.id)}>remove</button></li>)}</ol>}</Card>
  );
}

export function Twin({ caseId }: { caseId: string }) {
  const { toast } = useAuth(); const t = useLoad<any>(`/api/v1/cases/${caseId}/twin`); const [busy, setBusy] = useState(false);
  const rebuild = async () => { setBusy(true); try { await api(`/api/v1/cases/${caseId}/twin/rebuild`, { method: "POST" }); toast("New Case Twin version created"); t.reload(); } catch (e: any) { toast(e.message, "err"); } setBusy(false); };
  const c = t.data?.current;
  return (
    <Card title="Case Twin — structured, versioned case representation" actions={<Button onClick={rebuild} loading={busy}><RefreshCw className="h-4 w-4" />Rebuild</Button>}>
      {!c ? <Empty title="No Case Twin yet">Click Rebuild to snapshot parties, facts, events, documents, evidence, issues and approved authorities.</Empty> : <>
        <div className="mb-2 text-sm">Version <b>{c.version}</b> of {t.data.versions.length} · {new Date(c.created_at).toLocaleString()}</div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{["parties", "facts", "events", "documents", "evidence", "legal_issues", "authorities", "extracted_facts"].map((k) => <div key={k} className="rounded bg-ink-50 p-2 text-center"><div className="text-xl font-semibold">{c.data[k]?.length}</div><div className="text-xs text-ink-500">{k.replace("_", " ")} {c.data._delta_vs_previous?.[k] ? `(${c.data._delta_vs_previous[k] > 0 ? "+" : ""}${c.data._delta_vs_previous[k]})` : ""}</div></div>)}</div>
        <p className="mt-2 text-xs text-ink-500">{c.data.authorities_note}</p><details className="mt-2"><summary className="cursor-pointer text-sm">Raw JSON</summary><pre className="max-h-96 overflow-auto rounded bg-ink-900 p-3 text-xs text-green-200">{JSON.stringify(c.data, null, 2)}</pre></details></>}
    </Card>
  );
}

export function Intelligence({ caseId, caseType }: { caseId: string; caseType?: string }) {
  const { toast, user } = useAuth(); const runs = useLoad<any[]>(`/api/v1/workflows?case_id=${caseId}`); const reps = useLoad<any[]>(`/api/v1/reports?case_id=${caseId}`);
  const [side, setSide] = useState(""); const [asOf, setAsOf] = useState(""); const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); try { const r = await api(`/api/v1/cases/${caseId}/workflows/assessment`, { body: { client_side: side || null, as_of: asOf || null } }); toast(`Workflow ${r.status.replace("_", " ")}`, r.status === "failed" ? "err" : "ok"); runs.reload(); reps.reload(); } catch (e: any) { toast(e.message, "err"); } setBusy(false); };
  return (
    <div className="space-y-4">
      {user.role === "advocate" ? <Card title="Run multi-agent case assessment (LangGraph)"><div className="flex flex-wrap items-end gap-3"><div><Label>Your client's side (for adversarial review)</Label><Select value={side} onChange={(e: any) => setSide(e.target.value)}><option value="">Not specified</option>{["tenant", "landlord", "employee", "employer", "prosecution", "defence"].map((s) => <option key={s}>{s}</option>)}</Select></div><div><Label>Law as of (optional)</Label><Input type="date" value={asOf} onChange={(e: any) => setAsOf(e.target.value)} /></div><Button loading={busy} onClick={run}><Play className="h-4 w-4" />Run workflow</Button></div><p className="mt-2 text-xs text-ink-500">Document Analysis → Legal Research → Case Assessment → Adversarial Review → Citation Verification → human approval. No outcome probabilities are produced.</p></Card> : <Card><p className="text-sm text-ink-500">Only advocates can run assessments.</p></Card>}
      <Card title="Workflow runs">{!runs.data?.length ? <Empty /> : <Table head={["Started", "Kind", "Mode", "Status", ""]}>{runs.data.map((r) => <tr key={r.id}><Td>{new Date(r.created_at).toLocaleString()}</Td><Td>{r.kind.replace("_", " ")}</Td><Td><Badge tone="amber">{r.mode}</Badge></Td><Td><Status s={r.status} /></Td><Td><Link className="text-brand-600 underline" href={`/workflows?run=${r.id}`}>Open monitor</Link></Td></tr>)}</Table>}</Card>
      <Card title="Reports">{!reps.data?.length ? <Empty /> : <Table head={["Created", "Title", "Status", ""]}>{reps.data.map((r) => <tr key={r.id}><Td>{new Date(r.created_at).toLocaleString()}</Td><Td>{r.title}</Td><Td><Status s={r.status} /></Td><Td><Link className="text-brand-600 underline" href={`/reports/${r.id}`}>View</Link></Td></tr>)}</Table>}</Card>
    </div>
  );
}
