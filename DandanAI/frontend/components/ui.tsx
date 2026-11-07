"use client";
import clsx from "clsx";
import { Loader2, Inbox, AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export const Card = ({ title, actions, children, className }: any) => (
  <section className={clsx("rounded-lg border border-ink-200 bg-white shadow-sm", className)}>
    {(title || actions) && <header className="flex items-center justify-between gap-2 border-b border-ink-100 px-4 py-3"><h2 className="text-sm font-semibold text-ink-700">{title}</h2><div className="flex gap-2">{actions}</div></header>}
    <div className="p-4">{children}</div>
  </section>
);
export const Button = ({ variant = "primary", className, loading, children, ...p }: any) => (
  <button {...p} disabled={p.disabled || loading} className={clsx("inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:opacity-50",
    variant === "primary" && "bg-brand-600 text-white hover:bg-brand-700", variant === "ghost" && "text-ink-700 hover:bg-ink-100", variant === "outline" && "border border-ink-200 bg-white hover:bg-ink-50",
    variant === "danger" && "bg-red-600 text-white hover:bg-red-700", className)}>{loading && <Loader2 className="h-4 w-4 animate-spin" />}{children}</button>
);
const field = "w-full rounded-md border border-ink-200 bg-white px-3 py-1.5 text-sm focus:border-brand-500";
export const Input = (p: any) => <input {...p} className={clsx(field, p.className)} />;
export const Textarea = (p: any) => <textarea {...p} className={clsx(field, "min-h-[80px]", p.className)} />;
export const Select = ({ children, ...p }: any) => <select {...p} className={clsx(field, p.className)}>{children}</select>;
export const Label = ({ children, ...p }: any) => <label {...p} className="mb-1 block text-xs font-medium text-ink-500">{children}</label>;
export const Badge = ({ tone = "gray", children }: any) => (
  <span className={clsx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", { gray: "bg-ink-100 text-ink-700", green: "bg-emerald-100 text-emerald-800", amber: "bg-amber-100 text-amber-900", red: "bg-red-100 text-red-800", blue: "bg-brand-100 text-brand-700" }[tone as string])}>{children}</span>
);
export const toneFor = (s: string) => (/(approved|extracted$|ok|pass$|verified$|connected|live|human_verified|in_force|open$)/i.test(s) ? "green" : /(fail|reject|error|blocked|overdue|repealed)/i.test(s) ? "red" : /(warn|draft|await|pending|mock|synthetic|unverified|retry|due_soon|low|needs|candidate)/i.test(s) ? "amber" : "gray");
export const Status = ({ s }: { s: string }) => <Badge tone={toneFor(String(s))}>{String(s).replaceAll("_", " ")}</Badge>;
export const Spinner = ({ label = "Loading…" }: any) => <div className="flex items-center gap-2 p-6 text-sm text-ink-500"><Loader2 className="h-4 w-4 animate-spin" />{label}</div>;
export const Empty = ({ children, title = "Nothing here yet" }: any) => <div className="flex flex-col items-center gap-1 p-8 text-center text-sm text-ink-500"><Inbox className="h-6 w-6" /><div className="font-medium text-ink-700">{title}</div><div>{children}</div></div>;
export const ErrorBox = ({ error }: { error: any }) => error ? <div role="alert" className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{String(error.message || error)}</div> : null;
export const Table = ({ head, children }: any) => (
  <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b border-ink-200 text-xs uppercase text-ink-500">{head.map((h: string) => <th key={h} className="px-2 py-2 font-medium">{h}</th>)}</tr></thead><tbody className="divide-y divide-ink-100">{children}</tbody></table></div>
);
export const Td = ({ children, className }: any) => <td className={clsx("px-2 py-2 align-top", className)}>{children}</td>;
export const Page = ({ title, subtitle, actions, children }: any) => (
  <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6"><div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="font-serif text-2xl font-semibold">{title}</h1>{subtitle && <p className="text-sm text-ink-500">{subtitle}</p>}</div><div className="flex gap-2">{actions}</div></div>{children}</div>
);
export function Tabs({ tabs, value, onChange }: { tabs: [string, string][]; value: string; onChange: (v: string) => void }) {
  return <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-ink-200">{tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)} className={clsx("whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium", value === k ? "border-brand-600 text-brand-700" : "border-transparent text-ink-500 hover:text-ink-900")}>{l}</button>)}</div>;
}
export function useLoad<T = any>(path: string | null, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null); const [error, setError] = useState<any>(null); const [loading, setLoading] = useState(!!path);
  const reload = async () => { if (!path) return; setLoading(true); try { setData(await api(path)); setError(null); } catch (e) { setError(e); } setLoading(false); };
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [path, ...deps]);
  return { data, error, loading, reload, setData };
}
// Minimal safe markdown renderer (no HTML injection): headings, lists, tables, blockquotes, bold/italic
export function Markdown({ text }: { text: string }) {
  const inline = (s: string) => s.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g).map((p, i) => p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p.startsWith("*") && p.length > 2 ? <em key={i}>{p.slice(1, -1)}</em> : p.startsWith("`") ? <code key={i} className="rounded bg-ink-100 px-1">{p.slice(1, -1)}</code> : p);
  const lines = text.split("\n"); const out: any[] = []; let list: any[] = []; let tbl: string[][] = [];
  const flush = () => { if (list.length) { out.push(<ul key={out.length}>{list}</ul>); list = []; } if (tbl.length) { out.push(<div key={out.length} className="overflow-x-auto"><table><tbody>{tbl.filter(r => !r.every(c => /^-+$/.test(c.trim()))).map((r, i) => <tr key={i}>{r.map((c, j) => i === 0 ? <th key={j}>{inline(c.trim())}</th> : <td key={j}>{inline(c.trim())}</td>)}</tr>)}</tbody></table></div>); tbl = []; } };
  lines.forEach((l, i) => {
    if (l.startsWith("|")) { tbl.push(l.split("|").slice(1, -1)); return; } else if (tbl.length) flush();
    if (/^[-*] /.test(l)) { list.push(<li key={i}>{inline(l.slice(2))}</li>); return; } else if (list.length) flush();
    if (l.startsWith("### ")) out.push(<h3 key={i}>{inline(l.slice(4))}</h3>); else if (l.startsWith("## ")) out.push(<h2 key={i}>{inline(l.slice(3))}</h2>); else if (l.startsWith("# ")) out.push(<h1 key={i}>{inline(l.slice(2))}</h1>);
    else if (l.startsWith("> ")) out.push(<blockquote key={i}>{inline(l.slice(2))}</blockquote>); else if (l.trim() && l.trim() !== "---") out.push(<p key={i}>{inline(l)}</p>);
  }); flush();
  return <div className="prose-md">{out}</div>;
}
