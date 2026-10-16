"use client";

import React, { useEffect, useState } from "react";
import { Bookmark, CheckCircle2, Download, ExternalLink, Heart, MoreHorizontal, Share2 } from "@/components/ui/icons";
import { PaperDetail } from "@/lib/types";
import { api, fetchAuthBlobUrl, isAuthError } from "@/lib/api";
import { getDocumentTypeBadge } from "@/lib/utils";
import { getLikedPaperIds, getSavedPaperIds, toggleLikedPaper, toggleSavedPaper } from "@/lib/library";
import { ReportDialog } from "@/components/paper/ReportDialog";
import { useAuth } from "@/components/auth/AuthProvider";

interface PaperViewerProps {
  paper: PaperDetail;
}

// Session-scoped cache of viewer blob URLs (paperId:kind -> blob URL).
const readerBlobCache = new Map<string, string>();

export const PaperViewer: React.FC<PaperViewerProps> = ({ paper }) => {
  const { user, configured: authConfigured, signInWithGoogle } = useAuth();
  const [downloading, setDownloading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [liked, setLiked] = useState(false);  const [shared, setShared] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [readerBlobUrl, setReaderBlobUrl] = useState<string | null>(null);
  const [readerError, setReaderError] = useState<string | null>(null);
  const [readerLoading, setReaderLoading] = useState(true);
  const typeBadge = getDocumentTypeBadge(paper);
  const displayTitle = paper.title || paper.original_filename.replace(/\.[^/.]+$/, "");
  const hasRenderedPdf = paper.derivatives.some((derivative) => derivative.derivative_type === "final_pdf");
  const [viewMode, setViewMode] = useState<"refined" | "original">(hasRenderedPdf ? "refined" : "original");
  const latestRewriteLog = [...paper.processing_logs]
    .filter((log) => log.stage === "rewrite")
    .sort((a, b) => String(b.started_at || "").localeCompare(String(a.started_at || "")))[0];
  const hasCleanedPreview = latestRewriteLog?.metrics?.fallback === "cleaned_preprocess_fallback" || paper.status === "needs_review";
  const readerPath = (viewMode === "refined" && hasRenderedPdf)
    ? `/api/papers/${paper.id}/view/refined`
    : `/api/papers/${paper.id}/view/original`;
  const refinementMessage = hasCleanedPreview
    ? "AI refinement needs another pass. Showing a cleaned preview of the uploaded pages."
    : null;
  const uploadedDate = paper.created_at ? paper.created_at.slice(0, 10) : "Not specified";

  useEffect(() => {
    setSaved(getSavedPaperIds().includes(paper.id));
    setLiked(getLikedPaperIds().includes(paper.id));
  }, [paper.id]);

  // The viewer endpoints require auth — load the PDF as an authenticated blob.
  // Blob URLs are cached per paper+version so switching tabs/pages and coming
  // back is instant instead of re-downloading and reloading the iframe.
  const readerCacheKey = `${paper.id}:${viewMode}`;
  useEffect(() => {
    const userId = user?.id; // stable identity — token refreshes change the user object
    let cancelled = false;
    setReaderError(null);
    if (!userId) {
      setReaderBlobUrl(null);
      setReaderError("auth");
      setReaderLoading(false);
      return;
    }
    const cached = readerBlobCache.get(readerCacheKey);
    if (cached) {
      setReaderBlobUrl(cached);
      setReaderLoading(false);
      return;
    }
    setReaderBlobUrl(null);
    setReaderLoading(true);
    fetchAuthBlobUrl(readerPath, "application/pdf")
      .then((url) => {
        if (cancelled) { URL.revokeObjectURL(url); return; }
        // Simple FIFO cache — revoke the oldest beyond 6 entries.
        if (readerBlobCache.size >= 6) {
          const oldest = readerBlobCache.keys().next().value;
          if (oldest !== undefined) {
            const oldUrl = readerBlobCache.get(oldest);
            if (oldUrl) URL.revokeObjectURL(oldUrl);
            readerBlobCache.delete(oldest);
          }
        }
        readerBlobCache.set(readerCacheKey, url);
        setReaderBlobUrl(url);
      })
      .catch((error) => {
        if (!cancelled) setReaderError(isAuthError(error) ? "auth" : "Could not load this document.");
      })
      .finally(() => { if (!cancelled) setReaderLoading(false); });
    return () => { cancelled = true; };
  }, [paper.id, user?.id, readerCacheKey, readerPath]);

  const handleDownload = async (forceType?: "refined" | "original") => {
    const downloadType = forceType || (viewMode === "refined" && hasRenderedPdf ? "refined" : "original");
    setDownloading(true);
    try {
      const path = `/api/papers/${paper.id}/download/${downloadType}`;
      const blobUrl = await fetchAuthBlobUrl(path, downloadType === "original" ? undefined : "application/pdf");
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = downloadType === "refined" ? `${displayTitle}.pdf` : (paper.original_filename || `${displayTitle}-original`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 4000);
    } catch (error) {
      if (isAuthError(error)) setReaderError("auth");
    } finally {
      setTimeout(() => setDownloading(false), 1200);
    }
  };

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShared(true);
      setTimeout(() => setShared(false), 1600);
    } catch {
      window.prompt("Copy this document link", window.location.href);
    }
  };

  const openReport = () => {
    setMoreOpen(false);
    setReportOpen(true);
  };

  return (
    <div className="space-y-5">
      <section className="border-b border-[#e6e9e5] pb-5">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className={`rounded px-2 py-1 text-[10px] font-semibold ${typeBadge.bg} ${typeBadge.text}`}>{typeBadge.label}</span>
              {paper.course_code ? <span className="rounded bg-[#f1f3f0] px-2 py-1 font-mono text-[10px] font-semibold text-[#64716c]">{paper.course_code}</span> : null}
              <span className="flex items-center gap-1 text-[11px] text-[#899490]"><span className="h-1.5 w-1.5 rounded-full bg-[#5aa34f]" /> {hasCleanedPreview ? "Cleaned preview" : viewMode === "refined" ? "Refined Typeset" : "Original Upload"}</span>
            </div>
            <h1 className="max-w-4xl text-[25px] font-semibold leading-[1.18] tracking-[-0.035em] text-[#1f3035] sm:text-[30px]">{displayTitle}</h1>
            {paper.description ? <p className="mt-2 max-w-3xl text-[13px] leading-5 text-[#74807d]">{paper.description}</p> : null}
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[#77837f]">
              {paper.course_name ? <span>{paper.course_name}</span> : null}
              {paper.department ? <><span className="text-[#c2c9c5]">-</span><span>{paper.department}</span></> : null}
              {paper.study_year ? <><span className="text-[#c2c9c5]">-</span><span>{paper.study_year}</span></> : null}
              {paper.university ? <><span className="text-[#c2c9c5]">-</span><span>{paper.university}</span></> : null}
              {paper.year ? <><span className="text-[#c2c9c5]">-</span><span>{paper.year}</span></> : null}
              {paper.semester ? <><span className="text-[#c2c9c5]">-</span><span>{paper.semester}</span></> : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {hasRenderedPdf ? (
              <div className="mr-1 flex items-center rounded-lg border border-[#dfe6df] bg-[#f5f8f5] p-0.5 text-[11px] font-medium">
                <button
                  type="button"
                  onClick={() => setViewMode("refined")}
                  className={`flex items-center gap-1 rounded-md px-2.5 py-1.5 transition-colors ${
                    viewMode === "refined" ? "bg-white text-[#20362f] shadow-sm font-semibold" : "text-[#71807a] hover:text-[#20362f]"
                  }`}
                >
                  ✨ Refined
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("original")}
                  className={`flex items-center gap-1 rounded-md px-2.5 py-1.5 transition-colors ${
                    viewMode === "original" ? "bg-white text-[#20362f] shadow-sm font-semibold" : "text-[#71807a] hover:text-[#20362f]"
                  }`}
                >
                  📄 Original
                </button>
              </div>
            ) : null}
            <button type="button" onClick={() => { const nextLiked = toggleLikedPaper(paper.id); setLiked(nextLiked); if (user) { api.toggleLike(paper.id).then((result) => setLiked(result.liked)).catch(() => undefined); } else { void api.recordPaperInteraction(paper.id, nextLiked ? "like" : "unlike").catch(() => undefined); } }} className={`flex h-9 items-center gap-1.5 rounded-lg border px-3 text-[12px] font-medium transition-colors ${liked ? "border-[#edc3bb] bg-[#fff3f0] text-[#b75e51]" : "border-[#dfe6df] bg-white text-[#71807a] hover:text-[#b75e51]"}`}><Heart className={`h-4 w-4 ${liked ? "fill-current" : ""}`} />{liked ? "Liked" : "Like"}</button>
            <button type="button" onClick={() => { const nextSaved = toggleSavedPaper(paper.id); setSaved(nextSaved); if (user) { api.toggleSave(paper.id).then((result) => setSaved(result.saved)).catch(() => undefined); } else { void api.recordPaperInteraction(paper.id, nextSaved ? "save" : "unsave").catch(() => undefined); } }} className={`flex h-9 items-center gap-1.5 rounded-lg border px-3 text-[12px] font-medium transition-colors ${saved ? "border-[#bfd6b8] bg-[#edf7e9] text-[#3d843d]" : "border-[#dfe6df] bg-white text-[#71807a] hover:text-[#3d843d]"}`}><Bookmark className="h-4 w-4" />{saved ? "Saved" : "Save"}</button>
            <button type="button" onClick={handleShare} className="flex h-9 items-center gap-1.5 rounded-lg border border-[#dfe6df] bg-white px-3 text-[12px] font-medium text-[#71807a] transition-colors hover:text-[#3d843d]"><Share2 className="h-4 w-4" />{shared ? "Copied" : "Share"}</button>
            <div className="relative">
              <button type="button" aria-label="More actions" aria-expanded={moreOpen} onClick={() => setMoreOpen((value) => !value)} className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#dfe6df] bg-white text-[#71807a] hover:bg-[#f2f5f1]"><MoreHorizontal className="h-4 w-4" /></button>
              {moreOpen ? <><button type="button" aria-label="Close document actions" onClick={() => setMoreOpen(false)} className="fixed inset-0 z-40 bg-transparent" /><div className="absolute right-0 top-11 z-50 w-64 border border-[#dfe6df] bg-white p-1.5 shadow-[0_12px_30px_rgba(35,53,43,0.15)]">
                <p className="px-2.5 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9aa39f]">Document actions</p>
                <button type="button" onClick={openReport} className="block w-full px-2.5 py-2 text-left text-[12px] text-[#50615b] hover:bg-[#f4f7f3]">Report a problem</button>
                <div className="my-1 border-t border-[#edf0ed]" />
                <button type="button" onClick={handleShare} className="block w-full px-2.5 py-2 text-left text-[12px] text-[#50615b] hover:bg-[#f4f7f3]">Copy document link</button>
                {hasRenderedPdf ? (
                  <button
                    type="button"
                    onClick={() => { setMoreOpen(false); setViewMode(viewMode === "refined" ? "original" : "refined"); }}
                    className="block w-full px-2.5 py-2 text-left text-[12px] text-[#50615b] hover:bg-[#f4f7f3]"
                  >
                    {viewMode === "refined" ? "Switch to original upload" : "Switch to refined typeset"}
                  </button>
                ) : null}
              </div></> : null}
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_250px]">
        <section className="min-w-0 overflow-hidden bg-white">
          <div className="h-[650px] overflow-auto sm:h-[790px]">
            {readerError === "auth" ? (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center rounded-lg border border-dashed border-[#ccd8cc] bg-white p-8 text-center">
                <h3 className="text-[15px] font-bold text-[#2a3a3a]">Sign in to read this document</h3>
                <p className="mt-1.5 max-w-xs text-[12px] leading-5 text-[#7f8a87]">Reading and downloading is open to PaperFlow members. Browsing the library stays free.</p>
                <button type="button" onClick={() => signInWithGoogle(window.location.pathname)} disabled={!authConfigured} className="mt-4 flex items-center gap-2 rounded-lg bg-[#3e8d3c] px-4 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-[#337733] disabled:opacity-50">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true"><path fill="currentColor" d="M21.35 11.1H12v3.8h5.35c-.5 2.4-2.6 3.8-5.35 3.8a5.9 5.9 0 1 1 0-11.8c1.5 0 2.85.55 3.9 1.45l2.8-2.8A9.9 9.9 0 0 0 12 2a10 10 0 1 0 0 20c5.75 0 9.55-4.05 9.55-9.75 0-.4-.05-.8-.2-1.15Z"/></svg>
                  Continue with Google
                </button>
              </div>
            ) : readerError ? (
              <div className="flex h-full min-h-[300px] items-center justify-center text-[12px] text-[#a9655b]">{readerError}</div>
            ) : readerLoading || !readerBlobUrl ? (
              <div className="flex h-full min-h-[400px] items-center justify-center text-[12px] text-[#899490]">Loading document...</div>
            ) : (
              <div className="h-full"><iframe src={`${readerBlobUrl}#toolbar=1&navpanes=0`} className="h-full w-full border-0 bg-white" title={`${displayTitle} viewer`} /></div>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e7ebe7] px-4 py-3">
            {refinementMessage ? <span className="text-[11px] font-medium text-[#9a6a3d]">{refinementMessage}</span> : <span />}
            <div className="flex items-center gap-2">
              {hasRenderedPdf ? (
                <button
                  type="button"
                  onClick={() => setViewMode(viewMode === "refined" ? "original" : "refined")}
                  className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-[#6d7b75] hover:bg-[#f2f5f1]"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {viewMode === "refined" ? "View original upload" : "View refined typeset"}
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => handleDownload()}
                disabled={downloading}
                className="inline-flex items-center gap-1.5 rounded-md bg-[#3e8d3c] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#337733]"
              >
                {downloading ? <CheckCircle2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                {downloading ? "Preparing" : viewMode === "refined" && hasRenderedPdf ? "Download PDF" : "Download original"}
              </button>
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="border border-[#e1e7e1] bg-white p-4"><h2 className="text-[13px] font-semibold text-[#2d403c]">About this document</h2><dl className="mt-4 space-y-3">{[["Course", paper.course_name || paper.course_code || "Not specified"], ["Department", paper.department || "Not specified"], ["Study year", paper.study_year || "Not specified"], ["University", paper.university || "Not specified"], ["University type", paper.university_type || "Not specified"], ["Document year", paper.year || "Not specified"], ["Uploaded date", uploadedDate], ["Pages", paper.page_count ? `${paper.page_count} pages` : "Preview available"], ["Uploader", paper.uploader_name || paper.instructor || "PaperFlow contributor"]].map(([label, value]) => <div key={label} className="flex items-start justify-between gap-3 border-b border-[#eef1ee] pb-2.5 text-[11px]"><dt className="text-[#8a9591]">{label}</dt><dd className="max-w-[145px] text-right font-medium text-[#52625c]">{value}</dd></div>)}</dl>{paper.description ? <p className="mt-4 text-[11px] leading-4 text-[#74807d]">{paper.description}</p> : null}</div>
          <div className="border border-[#e1e7e1] bg-white p-4"><h2 className="text-[13px] font-semibold text-[#2d403c]">Keep exploring</h2><p className="mt-1 text-[11px] leading-4 text-[#84908c]">Save this paper to your library, then find more material from the same course.</p><button type="button" onClick={() => window.history.back()} className="mt-3 text-[11px] font-semibold text-[#4c814b] hover:text-[#2f6835]">Back to library -&gt;</button></div>
        </aside>
      </div>

      <ReportDialog paperId={paper.id} open={reportOpen} onClose={() => setReportOpen(false)} />
    </div>
  );
};
