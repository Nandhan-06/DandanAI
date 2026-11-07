"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button, Input, Label, ErrorBox, Badge } from "@/components/ui";

export default function Login() {
  const { login, status } = useAuth(); const router = useRouter();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [err, setErr] = useState<any>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); setErr(null); try { await login(email, password); router.replace("/"); } catch (x) { setErr(x); } setBusy(false); };
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-ink-900 to-brand-700 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow-xl">
        <div><div className="font-serif text-2xl font-semibold">DandanAI</div><p className="text-sm text-ink-500">Sign in to your legal workspace</p></div>
        {status && status.mode?.overall !== "live" && <Badge tone="amber">Mock mode — no live AI services</Badge>}
        <ErrorBox error={err} />
        <div><Label htmlFor="email">Email</Label><Input id="email" type="email" required autoComplete="username" value={email} onChange={(e: any) => setEmail(e.target.value)} /></div>
        <div><Label htmlFor="pw">Password</Label><Input id="pw" type="password" required autoComplete="current-password" value={password} onChange={(e: any) => setPassword(e.target.value)} /></div>
        <Button type="submit" loading={busy} className="w-full">Sign in</Button>
        <p className="text-center text-sm text-ink-500">No account? <Link className="text-brand-600 underline" href="/register">Register</Link></p>
      </form>
    </div>
  );
}
