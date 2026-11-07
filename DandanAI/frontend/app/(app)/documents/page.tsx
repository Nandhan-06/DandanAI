"use client";
import { useState } from "react";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { Empty, Page, Select, Label, useLoad } from "@/components/ui";

export default function Documents() {
  const cases = useLoad<any[]>("/api/v1/cases"); const [cid, setCid] = useState("");
  const id = cid || cases.data?.[0]?.id;
  return (
    <Page title="Document intelligence" subtitle="Upload, extract, classify, summarise, review and compare — every extracted fact keeps document and page provenance">
      {!cases.data?.length ? <Empty title="Create a case first">Documents always belong to a case.</Empty> : <>
        <div className="max-w-sm"><Label htmlFor="c">Case</Label><Select id="c" value={id} onChange={(e: any) => setCid(e.target.value)}>{cases.data.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</Select></div>
        <DocumentsPanel key={id} caseId={id} /></>}
    </Page>
  );
}
