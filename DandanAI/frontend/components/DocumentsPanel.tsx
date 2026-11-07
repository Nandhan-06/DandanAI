"use client";
import { useEffect, useState } from "react";
import { Upload, GitCompare, Download } from "lucide-react";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, Empty, ErrorBox, Select, Spinner, Status, Table, Td, useLoad, Badge, Input } from "./ui";

const KINDS = ["party", "date", "deadline", "amount", "clause", "obligation", "legal_ref", "duration", "missing", "risk"];

export function DocumentsPanel({ caseId }: { caseId: string }) {
  const { toast } = useAuth(); const { data: docs, loading, error, reload } = useLoad<any[]>(`/api/v1/cases/${caseId}/documents`);
  const [file, setFile] = useState<File | null>(null); const [docType, setDocType] = useState("auto"); const [busy, setBusy] = useState(false); const [sel, setSel] = useState<any>(null); const [cmp, setCmp] = useState<any>(null); const [pair, setPair] = useState<string[]>([]);
  useEffect(() => { if (docs?.some((d) => ["uploaded", "processing"].includes(d.processing_status))) { const t = setTimeout(reload, 1500); return () => clearTimeout(t); } }, [docs]);
  const upload = async (replaces?: string) => { if (!file) return; setBusy(true); const f = new FormData(); f.append("file", file); f.append("doc_type", docType); if (replaces) f.append("replaces_document_id", replaces);
    try { await api(`/api/v1/cases/${caseId}/documents`, { form: f }); toast("Uploaded — processing"); setFile(null); reload(); } catch (e: any) { toast(e.message, "err"); } setBusy(false); };
  const doCompare = async () => { try { setCmp(await api(`/api/v1/cases/${caseId}/documents/compare`, { body: { document_a: pair[0], document_b: pair[1] } })); } catch (e: any) { toast(e.message, "err"); } };
  return (
    <div className="space-y-4">
      <Card title="Upload document (PDF, DOCX, PNG, JPG)">
        <div className="flex flex-wrap items-end gap-3">
          <input aria-label="Choose file" type="file" accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] || null)} className="text-sm" />
          <Select className="!w-48" value={docType} onChange={(e: any) => setDocType(e.target.value)} aria-label="Document type"><option value="auto">Auto-classify</option>{["rental_agreement", "employment_agreement", "property_agreement", "legal_notice", "judgment", "complaint", "evidence", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</Select>
          <Button onClick={() => upload()} loading={busy} disabled={!file}><Upload className="h-4 w-4" />Upload</Button>
        </div>
      </Card>
      <ErrorBox error={error} />
      <Card title="Documents" actions={pair.length === 2 && <Button variant="outline" onClick={doCompare}><GitCompare className="h-4 w-4" />Compare selected</Button>}>
        {loading && !docs ? <Spinner /> : !docs?.length ? <Empty title="No documents">Upload an agreement, notice or evidence file.</Empty> :
          <Table head={["", "File", "Type", "v", "Status", "Pages", ""]}>{docs.map((d) => <tr key={d.id}>
            <Td><input type="checkbox" aria-label={`Select ${d.filename} for comparison`} checked={pair.includes(d.id)} onChange={(e) => setPair(e.target.checked ? [...pair, d.id].slice(-2) : pair.filter((x) => x !== d.id))} /></Td>
            <Td><button className="text-brand-600 underline" onClick={() => setSel(d)}>{d.filename}</button></Td><Td>{d.doc_type?.replace("_", " ")} {d.doc_type_source === "classifier" && <Badge>auto</Badge>}</Td><Td>{d.version}</Td>
            <Td><Status s={d.processing_status} />{d.processing_error && <div className="mt-1 text-xs text-amber-800">{d.processing_error}</div>}</Td><Td>{d.page_count ?? "–"}</Td>
            <Td><Button variant="ghost" aria-label="Download" onClick={() => download(`/api/v1/cases/${caseId}/documents/${d.id}/download`, d.filename)}><Download className="h-4 w-4" /></Button></Td></tr>)}</Table>}
      </Card>
      {cmp && <Card title={`Comparison: ${cmp.documents.join(" ↔ ")}`}><p className="mb-2 text-xs text-ink-500">{cmp.note}</p>
        {cmp.clause_differences.map((c: any) => <div key={c.clause} className="mb-2 rounded border border-ink-200 p-2 text-sm"><b>{c.clause}</b> <span className="text-xs text-ink-500">(similarity {c.similarity})</span><div className="grid gap-2 sm:grid-cols-2"><div className="bg-red-50 p-1">A p.{c.a_page}: {c.a}</div><div className="bg-emerald-50 p-1">B p.{c.b_page}: {c.b}</div></div></div>)}
        <div className="text-sm">Amounts only in A: {cmp.financial_terms.only_in_a.join(", ") || "–"} · only in B: {cmp.financial_terms.only_in_b.join(", ") || "–"}</div>
        <div className="text-sm">Clauses only in A: {cmp.clauses_only_in_a.map((x: any) => x.clause).join(", ") || "–"} · only in B: {cmp.clauses_only_in_b.map((x: any) => x.clause).join(", ") || "–"}</div>
        {cmp.potential_inconsistencies.map((i: any, k: number) => <div key={k} className="text-sm"><Badge tone="amber">AI-inferred</Badge> {i.value}</div>)}</Card>}
      {sel && <DocDetail caseId={caseId} doc={sel} onClose={() => setSel(null)} onNewVersion={upload} />}
    </div>
  );
}

function DocDetail({ caseId, doc, onClose, onNewVersion }: any) {
  const { toast } = useAuth(); const [kind, setKind] = useState("party"); const ex = useLoad<any[]>(`/api/v1/cases/${caseId}/documents/${doc.id}/extractions`); const txt = useLoad<any>(`/api/v1/cases/${caseId}/documents/${doc.id}/text`); const ver = useLoad<any[]>(`/api/v1/cases/${caseId}/documents/${doc.id}/versions`);
  const review = async (e: any, status: string) => { let edited: string | undefined; if (status === "edited") { edited = prompt("Corrected value", e.edited_value || e.value) || undefined; if (!edited) return; } try { await api(`/api/v1/cases/${caseId}/documents/${doc.id}/extractions/${e.id}`, { method: "PATCH", body: { review_status: status, edited_value: edited } }); ex.reload(); } catch (x: any) { toast(x.message, "err"); } };
  const items = (ex.data || []).filter((e) => e.kind === kind);
  return (
    <Card title={`${doc.filename} — intelligence`} actions={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      {doc.summary?.narrative && <p className="mb-2 text-sm"><Badge tone="amber">{doc.summary.narrative_mode}</Badge> {doc.summary.narrative}</p>}
      <div className="mb-2 text-xs text-ink-500">Versions: {ver.data?.map((v) => `v${v.version}`).join(", ")}</div>
      <div className="mb-3 flex flex-wrap gap-1">{KINDS.map((k) => <button key={k} onClick={() => setKind(k)} className={`rounded-full px-3 py-1 text-xs ${kind === k ? "bg-brand-600 text-white" : "bg-ink-100"}`}>{k.replace("_", " ")} ({(ex.data || []).filter((e) => e.kind === k).length})</button>)}</div>
      {!items.length ? <Empty title="None found" /> : <Table head={["Value", "Label", "Page", "Origin", "Review", ""]}>{items.map((e) => <tr key={e.id}><Td>{e.edited_value || e.value}</Td><Td>{e.label}</Td><Td>{e.page ?? "–"}</Td><Td><Badge tone={e.origin === "explicit" ? "green" : "amber"}>{e.origin === "explicit" ? "in document" : "AI-inferred"}</Badge></Td><Td><Status s={e.review_status} /></Td>
        <Td><div className="flex gap-1"><Button variant="outline" onClick={() => review(e, "confirmed")}>Confirm</Button><Button variant="outline" onClick={() => review(e, "edited")}>Edit</Button><Button variant="outline" onClick={() => review(e, "rejected")}>Reject</Button></div></Td></tr>)}</Table>}
      <details className="mt-3"><summary className="cursor-pointer text-sm font-medium">Page text (provenance)</summary>{txt.data?.pages?.map((p: any) => <div key={p.page} className="mt-2"><div className="text-xs font-semibold text-ink-500">Page {p.page}{p.ocr && " (OCR)"}</div><pre className="whitespace-pre-wrap rounded bg-ink-50 p-2 text-xs">{p.text || "(no text)"}</pre></div>)}</details>
    </Card>
  );
}
