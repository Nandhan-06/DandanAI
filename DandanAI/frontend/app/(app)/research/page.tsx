"use client";
import { useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import { CitationCard } from "@/components/Citation";
import { Button, Badge, Card, Empty, ErrorBox, Input, Label, Page, Spinner } from "@/components/ui";

export default function Research() {
  const [q, setQ] = useState(""); const [j, setJ] = useState(""); const [asOf, setAsOf] = useState(""); const [hist, setHist] = useState(false); const [res, setRes] = useState<any>(null); const [err, setErr] = useState<any>(null); const [busy, setBusy] = useState(false);
  const go = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setErr(null); try { setRes(await api("/api/v1/research/search", { body: { query: q, jurisdiction: j || null, as_of: asOf || null, include_historical: hist, top_k: 8 } })); } catch (x) { setErr(x); } setBusy(false); };
  return (
    <Page title="Legal research" subtitle="Hybrid BM25 + vector retrieval with jurisdiction and date filters. Returns retrieved sources only — never invented authorities.">
      <Card><form onSubmit={go} className="grid gap-3 sm:grid-cols-4"><div className="sm:col-span-4"><Label htmlFor="q">Query</Label><Input id="q" required minLength={3} value={q} onChange={(e: any) => setQ(e.target.value)} placeholder="e.g. security deposit refund by landlord" /></div>
        <div><Label htmlFor="j">Jurisdiction</Label><Input id="j" value={j} onChange={(e: any) => setJ(e.target.value)} placeholder="India, Karnataka…" /></div><div><Label htmlFor="d">Law as of</Label><Input id="d" type="date" value={asOf} onChange={(e: any) => setAsOf(e.target.value)} /></div>
        <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={hist} onChange={(e) => setHist(e.target.checked)} />include repealed / historical</label><div className="flex items-end"><Button type="submit" loading={busy}><Search className="h-4 w-4" />Search</Button></div></form></Card>
      <ErrorBox error={err} />{busy && <Spinner label="Searching…" />}
      {res && <><div className="flex flex-wrap items-center gap-2 text-sm"><Badge tone={res.confidence === "none" ? "red" : res.confidence === "low" ? "amber" : "green"}>retrieval support: {res.confidence}</Badge><span className="text-ink-500">{res.confidence_note}</span><span>Jurisdictions searched: {res.jurisdictions_searched.join(", ")} · candidates: {res.candidates_considered}</span></div>
        {res.coverage_gaps.map((g: string) => <div key={g} className="rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900">⚠ {g}</div>)}
        {!res.hits.length ? <Empty title="No supporting source found">The knowledge base has nothing sufficient for this query. No legal conclusion is offered.</Empty> : <div className="space-y-3">{res.hits.map((h: any) => <CitationCard key={h.citation.chunk_id} c={h.citation} extra={<div className="mt-1 text-xs text-ink-500">bm25 {h.bm25} · vector {h.vector}</div>} />)}</div>}<p className="text-xs text-ink-500">{res.disclaimer}</p></>}
    </Page>
  );
}
