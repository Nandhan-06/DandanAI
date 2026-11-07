"use client";
import Link from "next/link";
import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Page, Select, Spinner, Status, Table, Td, Textarea, useLoad } from "@/components/ui";

export default function Cases() {
  const { user, toast } = useAuth(); const [q, setQ] = useState(""); const [st, setSt] = useState(""); const [show, setShow] = useState(false);
  const { data, loading, error, reload } = useLoad<any[]>(`/api/v1/cases?${new URLSearchParams({ ...(q && { q }), ...(st && { status: st }) })}`);
  const [f, setF] = useState({ title: "", case_type: "civil", jurisdiction: "India", description: "", is_synthetic: false });
  const create = async (e: React.FormEvent) => { e.preventDefault(); try { await api("/api/v1/cases", { body: f }); toast("Case created"); setShow(false); setF({ ...f, title: "", description: "" }); reload(); } catch (x: any) { toast(x.message, "err"); } };
  return (
    <Page title="Cases" subtitle="Each case is isolated to its owner and explicitly shared colleagues" actions={user.role !== "admin" && <Button onClick={() => setShow(!show)}><Plus className="h-4 w-4" />New case</Button>}>
      {show && <Card title="New case"><form onSubmit={create} className="grid gap-3 sm:grid-cols-2"><div><Label htmlFor="t">Title</Label><Input id="t" required value={f.title} onChange={(e: any) => setF({ ...f, title: e.target.value })} /></div>
        <div><Label htmlFor="ty">Type</Label><Select id="ty" value={f.case_type} onChange={(e: any) => setF({ ...f, case_type: e.target.value })}>{["civil", "criminal", "tenancy", "employment", "property", "consumer", "other"].map((t) => <option key={t}>{t}</option>)}</Select></div>
        <div><Label htmlFor="j">Jurisdiction (India or a State/UT)</Label><Input id="j" value={f.jurisdiction} onChange={(e: any) => setF({ ...f, jurisdiction: e.target.value })} /></div>
        <div className="flex items-end"><label className="text-sm"><input type="checkbox" checked={f.is_synthetic} onChange={(e) => setF({ ...f, is_synthetic: e.target.checked })} /> synthetic / demo case</label></div>
        <div className="sm:col-span-2"><Label htmlFor="d">Description</Label><Textarea id="d" value={f.description} onChange={(e: any) => setF({ ...f, description: e.target.value })} /></div><div className="sm:col-span-2"><Button type="submit">Create case</Button></div></form></Card>}
      <Card><div className="mb-3 flex flex-wrap gap-2"><div className="relative flex-1"><Search className="absolute left-2 top-2.5 h-4 w-4 text-ink-500" /><Input className="!pl-8" placeholder="Search cases…" aria-label="Search cases" value={q} onChange={(e: any) => setQ(e.target.value)} /></div><Select className="!w-40" aria-label="Status filter" value={st} onChange={(e: any) => setSt(e.target.value)}><option value="">All statuses</option><option value="open">Open</option><option value="archived">Archived</option></Select></div>
        <ErrorBox error={error} />{loading && !data ? <Spinner /> : !data?.length ? <Empty title="No cases">{user.role === "admin" ? "Admins manage users; case content is not visible to admin accounts." : "Create your first case to begin."}</Empty> :
          <Table head={["Case", "Type", "Jurisdiction", "Status", "Updated"]}>{data.map((c) => <tr key={c.id}><Td><Link className="font-medium text-brand-600 hover:underline" href={`/cases/${c.id}`}>{c.title}</Link> {!c.is_owner && <Badge tone="blue">shared</Badge>} {c.is_synthetic && <Badge tone="amber">synthetic</Badge>}</Td><Td>{c.case_type}</Td><Td>{c.jurisdiction}</Td><Td><Status s={c.status} /></Td><Td>{new Date(c.updated_at).toLocaleDateString()}</Td></tr>)}</Table>}</Card>
    </Page>
  );
}
