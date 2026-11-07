"use client";
import { useParams } from "next/navigation";
import { Download } from "lucide-react";
import { download } from "@/lib/api";
import { Badge, Button, Card, ErrorBox, Markdown, Page, Spinner, Status, useLoad } from "@/components/ui";

export default function Report() {
  const { id } = useParams<{ id: string }>(); const { data, error, loading } = useLoad<any>(`/api/v1/reports/${id}`);
  if (loading && !data) return <Spinner />; if (error) return <div className="p-6"><ErrorBox error={error} /></div>; const r = data;
  return (
    <Page title={r.title} subtitle={`Generated ${new Date(r.created_at).toLocaleString()}`} actions={<><Status s={r.status} /><Badge tone="amber">{r.mode} mode</Badge>{["pdf", "docx", "md"].map((f) => <Button key={f} variant="outline" onClick={() => download(`/api/v1/reports/${id}/export?format=${f}`, `dandanai-report.${f}`)}><Download className="h-4 w-4" />{f.toUpperCase()}</Button>)}</>}>
      <Card><Markdown text={r.markdown} />{r.review_note && <p className="mt-3 text-sm"><b>Review note:</b> {r.review_note}</p>}</Card>
      {r.run_id && <a className="text-sm text-brand-600 underline" href={`/workflows?run=${r.run_id}`}>Open the agent run for approval / history</a>}
    </Page>
  );
}
