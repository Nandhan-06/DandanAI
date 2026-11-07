"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Button, Card, Input, Label, Page, Select } from "@/components/ui";

export default function Settings() {
  const { user, status, toast, refresh, logout } = useAuth(); const [name, setName] = useState(user.full_name); const [bar, setBar] = useState(user.bar_council_id || ""); const [pref, setPref] = useState(user.preferences?.default_jurisdiction || "India"); const [cur, setCur] = useState(""); const [nw, setNw] = useState("");
  const save = async () => { try { await api("/api/v1/auth/me", { method: "PATCH", body: { full_name: name, bar_council_id: bar, preferences: { ...user.preferences, default_jurisdiction: pref } } }); toast("Profile saved"); refresh(); } catch (e: any) { toast(e.message, "err"); } };
  const pw = async () => { try { await api("/api/v1/auth/me", { method: "PATCH", body: { current_password: cur, new_password: nw } }); toast("Password changed — please sign in again"); logout(); } catch (e: any) { toast(e.message, "err"); } };
  return (
    <Page title="Settings" subtitle={`${user.email} · ${user.role.replace("_", " ")}`}>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Profile"><div className="space-y-3"><div><Label htmlFor="n">Full name</Label><Input id="n" value={name} onChange={(e: any) => setName(e.target.value)} /></div><div><Label htmlFor="b">Bar council enrolment no.</Label><Input id="b" value={bar} onChange={(e: any) => setBar(e.target.value)} /></div><div><Label htmlFor="j">Default jurisdiction</Label><Input id="j" value={pref} onChange={(e: any) => setPref(e.target.value)} /></div><Button onClick={save}>Save</Button></div></Card>
        <Card title="Change password"><div className="space-y-3"><div><Label htmlFor="c">Current password</Label><Input id="c" type="password" autoComplete="current-password" value={cur} onChange={(e: any) => setCur(e.target.value)} /></div><div><Label htmlFor="w">New password</Label><Input id="w" type="password" autoComplete="new-password" value={nw} onChange={(e: any) => setNw(e.target.value)} /></div><Button onClick={pw} disabled={!cur || nw.length < 10}>Change password</Button></div></Card>
        <Card title="Organisation">{user.organisation?.code ? <p className="text-sm">Join code: <b className="font-mono">{user.organisation.code}</b> — share with colleagues so they can register into your organisation.</p> : <p className="text-sm text-ink-500">{user.organisation?.name}</p>}</Card>
        <Card title="Provider modes (from server)"><div className="flex flex-wrap gap-2">{status && Object.entries(status.mode).map(([k, v]: any) => <Badge key={k} tone={v === "live" ? "green" : "amber"}>{k}: {v}</Badge>)}</div><p className="mt-2 text-xs text-ink-500">Set provider keys in the backend <code>.env</code>; the browser never holds API keys.</p></Card>
      </div>
    </Page>
  );
}
