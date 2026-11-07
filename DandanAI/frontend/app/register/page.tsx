"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button, Input, Label, Select, ErrorBox } from "@/components/ui";

export default function Register() {
  const { register } = useAuth(); const router = useRouter();
  const [f, setF] = useState({ full_name: "", email: "", password: "", role: "advocate", organisation_code: "", organisation_name: "" });
  const [err, setErr] = useState<any>(null); const [busy, setBusy] = useState(false); const [code, setCode] = useState("");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setErr(null);
    try { const body: any = { ...f }; if (!body.organisation_code) delete body.organisation_code; if (!body.organisation_name) delete body.organisation_name; const r = await register(body); setCode(r.organisation_code); setTimeout(() => router.replace("/"), 2500); } catch (x) { setErr(x); } setBusy(false); };
  if (code) return <div className="flex min-h-screen items-center justify-center p-4"><div className="max-w-sm rounded-xl bg-white p-6 shadow">Account created. Your organisation code is <b className="font-mono">{code}</b> — share it with colleagues so they can join your organisation. Redirecting…</div></div>;
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-ink-900 to-brand-700 p-4">
      <form onSubmit={submit} className="w-full max-w-md space-y-3 rounded-xl bg-white p-6 shadow-xl">
        <div className="font-serif text-2xl font-semibold">Create your account</div><ErrorBox error={err} />
        <div><Label htmlFor="n">Full name</Label><Input id="n" required value={f.full_name} onChange={set("full_name")} /></div>
        <div><Label htmlFor="e">Email</Label><Input id="e" type="email" required value={f.email} onChange={set("email")} /></div>
        <div><Label htmlFor="p">Password (10+ chars, letters and digits)</Label><Input id="p" type="password" required minLength={10} autoComplete="new-password" value={f.password} onChange={set("password")} /></div>
        <div><Label htmlFor="r">Role</Label><Select id="r" value={f.role} onChange={set("role")}><option value="advocate">Advocate</option><option value="legal_assistant">Legal assistant</option></Select><p className="mt-1 text-xs text-ink-500">Administrator accounts cannot be self-registered.</p></div>
        <div className="grid grid-cols-2 gap-2"><div><Label htmlFor="oc">Join organisation (code)</Label><Input id="oc" placeholder="ORG-XXXXXXXX" value={f.organisation_code} onChange={set("organisation_code")} /></div><div><Label htmlFor="on">…or new organisation name</Label><Input id="on" value={f.organisation_name} onChange={set("organisation_name")} /></div></div>
        <Button type="submit" loading={busy} className="w-full">Register</Button>
        <p className="text-center text-sm text-ink-500">Have an account? <Link className="text-brand-600 underline" href="/login">Sign in</Link></p>
      </form>
    </div>
  );
}
