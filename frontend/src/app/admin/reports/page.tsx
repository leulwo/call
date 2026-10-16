"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "@/components/ui/icons";
import { api } from "@/lib/api";

interface ReportRow {
  id: string;
  paper_id: string;
  paper_title: string;
  paper_status: string | null;
  reason: string;
  details: string | null;
  status: string;
  review_note: string | null;
  created_at: string | null;
}

const STATUS_STYLES: Record<string, string> = {
  open: "bg-[#f8edd2] text-[#76551d]",
  reviewing: "bg-[#e6eef1] text-[#426572]",
  regenerating: "bg-[#e6efdf] text-[#4f7848]",
  needs_human: "bg-[#f6e4da] text-[#8c4d35]",
  resolved: "bg-[#eaf2e5] text-[#477044]",
  rejected: "bg-[#f0e3de] text-[#8b5444]",
};

export default function AdminReportsPage() {
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = new URL(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/reports`);
      if (statusFilter) url.searchParams.set("status", statusFilter);
      const res = await fetch(url.toString(), { cache: "no-store" });
      if (!res.ok) throw new Error(`Failed: ${res.statusText}`);
      setReports(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const act = async (reportId: string, action: () => Promise<unknown>) => {
    setBusyId(reportId);
    try {
      await action();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="border-b border-[#e6e9e5] pb-6">
        <p className="mb-3 text-[11px] font-medium text-[#82908b]">PaperFlow / Moderation</p>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <h1 className="text-[30px] font-semibold tracking-[-0.04em] text-[#1f3035]">Reports</h1>
            <p className="mt-2 text-[13px] text-[#74807d]">Accuracy reports regenerate the document with the report as prompt; removal requests are AI-adjudicated. Anything ambiguous lands here as needs-human.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="border border-[#dfe6df] bg-white px-2.5 py-2 text-[11px] text-[#4c5b56]">
              <option value="">All statuses</option>
              {["open", "reviewing", "regenerating", "needs_human", "resolved", "rejected"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button type="button" onClick={load} className="rounded-md border border-[#e1e6e1] bg-white p-2 text-[#71807a] hover:text-[#3d843d]" aria-label="Refresh"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
          </div>
        </div>
      </section>

      {error ? <p className="rounded-lg border border-[#edc3bb] bg-[#fff3f0] p-3 text-[12px] text-[#a9655b]">{error}</p> : null}

      {loading ? (
        <div className="min-h-40 animate-pulse rounded-xl bg-[#eef1ed]" />
      ) : reports.length === 0 ? (
        <div className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center text-[13px] text-[#7f8a87]">No reports {statusFilter ? `with status "${statusFilter}"` : "yet"}.</div>
      ) : (
        <section className="space-y-3">
          {reports.map((report) => (
            <article key={report.id} className="border border-[#dfe7df] bg-white p-4 shadow-[0_3px_12px_rgba(42,62,47,0.04)]">
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STATUS_STYLES[report.status] || "bg-[#f1f3f0] text-[#64716c]"}`}>{report.status}</span>
                    <span className="text-[10px] text-[#98a19f]">{report.created_at?.slice(0, 16).replace("T", " ") || ""}</span>
                  </div>
                  <h2 className="mt-1.5 truncate text-[14px] font-semibold text-[#2c3d3e]">
                    <Link href={`/papers/${report.paper_id}`} className="hover:text-[#3e7c3e]">{report.paper_title}</Link>
                    <span className="ml-2 text-[10px] font-normal text-[#98a19f]">({report.paper_status || "?"})</span>
                  </h2>
                  <p className="mt-0.5 text-[12px] font-medium text-[#52625c]">{report.reason}</p>
                  {report.details ? <p className="mt-1 text-[12px] leading-5 text-[#74807d]">{report.details}</p> : null}
                  {report.review_note ? <p className="mt-2 rounded-md bg-[#f7faf5] p-2 text-[11px] leading-4 text-[#4f6b52]">{report.review_note}</p> : null}
                </div>
                <div className="flex shrink-0 flex-wrap gap-1.5">
                  <button type="button" disabled={busyId === report.id} onClick={() => act(report.id, () => api._regenerateFromReport(report.id))} className="rounded-md border border-[#cfe0cb] px-2.5 py-1.5 text-[11px] font-semibold text-[#4c7948] hover:bg-[#edf5ea] disabled:opacity-40">Regenerate</button>
                  <button type="button" disabled={busyId === report.id} onClick={() => act(report.id, () => api._adjudicateReport(report.id))} className="rounded-md border border-[#d9e0da] px-2.5 py-1.5 text-[11px] font-medium text-[#52625c] hover:bg-[#f3f8f1] disabled:opacity-40">Re-adjudicate</button>
                  <button type="button" disabled={busyId === report.id} onClick={() => act(report.id, () => api._removeReportedPaper(report.id))} className="rounded-md border border-[#edc3bb] px-2.5 py-1.5 text-[11px] font-semibold text-[#b75e51] hover:bg-[#fff3f0] disabled:opacity-40">Remove paper</button>
                  <button type="button" disabled={busyId === report.id} onClick={() => act(report.id, () => api._setReportStatus(report.id, "resolved", "Manually resolved."))} className="rounded-md border border-[#e1e6e1] px-2.5 py-1.5 text-[11px] font-medium text-[#52625c] hover:bg-[#f2f5f1] disabled:opacity-40">Resolve</button>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
