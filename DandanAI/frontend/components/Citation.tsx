"use client";
import { Badge } from "./ui";

export function CitationCard({ c, extra }: { c: any; extra?: any }) {
  return (
    <div className="rounded-lg border border-ink-200 p-3 text-sm"><div className="flex flex-wrap items-center gap-1"><b>{c.title}</b><Badge tone={c.authority_class === "primary" ? "blue" : "gray"}>{c.authority_class}</Badge>{c.is_synthetic && <Badge tone="amber">SYNTHETIC TEST DATA</Badge>}<Badge tone={c.verification_status === "human_verified" ? "green" : "amber"}>{c.verification_status.replaceAll("_", " ")}</Badge>{c.status !== "in_force" && <Badge tone="red">{c.status}</Badge>}</div>
      <div className="text-xs text-ink-500">{[c.pinpoint, c.court, c.citation, c.jurisdiction, c.date, c.instrument_type].filter(Boolean).join(" · ")}</div><p className="mt-1">{c.excerpt}</p>{c.source_url && <a className="text-xs text-brand-600 underline" href={c.source_url} target="_blank" rel="noreferrer">source link</a>}{extra}</div>
  );
}

