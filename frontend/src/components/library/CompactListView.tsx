"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Bookmark, CheckCircle2, Download, FileText, Heart } from "@/components/ui/icons";
import { PaperSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { getDocumentTypeBadge } from "@/lib/utils";
import { toggleLikedPaper, toggleSavedPaper } from "@/lib/library";

interface CompactListViewProps { papers: PaperSummary[]; }

export const CompactListView: React.FC<CompactListViewProps> = ({ papers }) => {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const handleDownload = async (paper: PaperSummary) => {
    setDownloadingId(paper.id);
    try { await api.triggerDirectDownload(paper.id, "refined", `${paper.title || paper.original_filename}.pdf`); }
    finally { setTimeout(() => setDownloadingId(null), 1200); }
  };
  if (!papers.length) return null;

  return (
    <div className="overflow-hidden border border-[#e1e7e1] bg-white">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left">
          <thead className="border-b border-[#e6eae6] bg-[#f8faf8] text-[10px] font-semibold uppercase tracking-[0.13em] text-[#85908c]"><tr><th className="px-4 py-3">Document</th><th className="px-3 py-3">Course / university</th><th className="px-3 py-3">Year</th><th className="px-3 py-3">Type</th><th className="px-4 py-3 text-right">Actions</th></tr></thead>
          <tbody className="divide-y divide-[#edf0ed]">
            {papers.map((paper) => { const type = getDocumentTypeBadge(paper); const title = paper.title || paper.original_filename; const isDownloading = downloadingId === paper.id; return <tr key={paper.id} className="group transition-colors hover:bg-[#fafcf9]">
              <td className="px-4 py-3"><Link href={`/papers/${paper.id}`} className="flex items-center gap-3"><span className="flex h-9 w-8 shrink-0 items-center justify-center rounded bg-[#edf3e9] text-[#5e8758]"><FileText className="h-4 w-4" /></span><span className="min-w-0"><span className="block max-w-[320px] truncate text-[13px] font-semibold text-[#2c3b3f] group-hover:text-[#3f7d40]">{title}</span><span className="mt-0.5 block max-w-[320px] truncate text-[11px] text-[#899490]">{paper.course_name || "Academic document"}</span></span></Link></td>
              <td className="px-3 py-3 text-[11px] text-[#64716e]">{[paper.course_code, paper.university].filter(Boolean).join(" · ") || "—"}</td>
              <td className="px-3 py-3 text-[11px] text-[#64716e]">{paper.year || "—"}</td>
              <td className="px-3 py-3"><span className={`rounded px-1.5 py-1 text-[10px] font-medium ${type.bg} ${type.text}`}>{type.label}</span></td>
              <td className="px-4 py-3"><div className="flex items-center justify-end gap-1"><button type="button" onClick={() => { const next = toggleLikedPaper(paper.id); void api.recordPaperInteraction(paper.id, next ? "like" : "unlike"); }} aria-label="Like document" className="rounded-md p-1.5 text-[#8e9995] hover:bg-[#fff2ef] hover:text-[#bd6759]"><Heart className="h-3.5 w-3.5" /></button><button type="button" onClick={() => { const next = toggleSavedPaper(paper.id); void api.recordPaperInteraction(paper.id, next ? "save" : "unsave"); }} aria-label="Save document" className="rounded-md p-1.5 text-[#8e9995] hover:bg-[#edf7e9] hover:text-[#3d843d]"><Bookmark className="h-3.5 w-3.5" /></button><button type="button" onClick={() => handleDownload(paper)} disabled={isDownloading} className="ml-1 flex items-center gap-1 rounded-md border border-[#cfe0cb] px-2 py-1.5 text-[10px] font-semibold text-[#4c7948] hover:bg-[#edf5ea]">{isDownloading ? <CheckCircle2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />} PDF</button></div></td>
            </tr>; })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
