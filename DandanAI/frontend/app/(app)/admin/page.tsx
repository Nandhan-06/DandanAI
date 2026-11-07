"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, ErrorBox, Input, Label, Page, Select, Spinner, Status, Table, Td, useLoad } from "@/components/ui";

export default function Admin() {
  const { user, toast } = useAuth(); const users = useLoad<any[]>(user.role === "admin" ? "/api/v1/admin/users" : null); const stats = useLoad<any>(user.role === "admin" ? "/api/v1/admin/stats" : null); const audit = useLoad<any[]>(user.role === "admin" ? "/api/v1/admin/audit?limit=60" : null);
  const [f, setF] = useState({ email: "", password: "", full_name: "", role: "advocate" });
  if (user.role !== "admin") return <Page title="Admin"><ErrorBox error="Administrator access required." /></Page>;
  const create = async (e: React.FormEvent) => { e.preventDefault(); try { await api("/api/v1/admin/users", { body: f }); toast("User created"); setF({ email: "", password: "", full_name: "", role: "advocate" }); users.reload(); } catch (x: any) { toast(x.message, "err"); } };
  const patch = async (id: string, body: any) => { try { await api(`/api/v1/admin/users/${id}`, { method: "PATCH", body }); users.reload(); } catch (x: any) { toast(x.message, "err"); } };
  return (
    <Page title="Administration" subtitle={stats.data ? `Organisation ${stats.data.organisation.name} — join code ${stats.data.organisation.code}` : ""}>
      <Card title="Create user (admin-only path for creating administrators)"><form onSubmit={create} className="grid gap-3 sm:grid-cols-5"><div><Label>Name</Label><Input required value={f.full_name} onChange={(e: any) => setF({ ...f, full_name: e.target.value })} /></div><div><Label>Email</Label><Input type="email" required value={f.email} onChange={(e: any) => setF({ ...f, email: e.target.value })} /></div><div><Label>Password</Label><Input type="password" required minLength={10} value={f.password} onChange={(e: any) => setF({ ...f, password: e.target.value })} /></div><div><Label>Role</Label><Select value={f.role} onChange={(e: any) => setF({ ...f, role: e.target.value })}><option value="advocate">advocate</option><option value="legal_assistant">legal assistant</option><option value="admin">admin</option></Select></div><div className="flex items-end"><Button type="submit">Create</Button></div></form></Card>
      <Card title="Users">{users.loading && !users.data ? <Spinner /> : <Table head={["Name", "Email", "Role", "Active", ""]}>{users.data?.map((u) => <tr key={u.id}><Td>{u.full_name}</Td><Td>{u.email}</Td><Td><Select className="!w-40" value={u.role} aria-label={`Role for ${u.email}`} onChange={(e: any) => patch(u.id, { role: e.target.value })}><option value="advocate">advocate</option><option value="legal_assistant">legal_assistant</option><option value="admin">admin</option></Select></Td><Td><Status s={u.is_active ? "active" : "disabled"} /></Td><Td><Button variant="outline" onClick={() => patch(u.id, { is_active: !u.is_active })}>{u.is_active ? "Deactivate" : "Activate"}</Button></Td></tr>)}</Table>}<p className="mt-2 text-xs text-ink-500">Admins manage users and see counts; case content is not accessible to admin accounts.</p></Card>
      <Card title="Audit trail">{!audit.data ? <Spinner /> : <div className="max-h-80 overflow-auto"><Table head={["Time", "Action", "Resource", "Detail"]}>{audit.data.map((a) => <tr key={a.id}><Td className="whitespace-nowrap text-xs">{new Date(a.created_at).toLocaleString()}</Td><Td>{a.action}</Td><Td className="text-xs">{a.resource_type}</Td><Td className="text-xs">{a.detail ? JSON.stringify(a.detail).slice(0, 90) : ""}</Td></tr>)}</Table></div>}</Card>
    </Page>
  );
}
