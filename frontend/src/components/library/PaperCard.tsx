"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { Bookmark, CheckCircle2, Download, FileText, Heart, MoreHorizontal, X } from "@/components/ui/icons";
import { PaperSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { getDocumentTypeBadge } from "@/lib/utils";
import { addPaperToCollection, getCollections, getLikedPaperIds, getSavedPaperIds, LibraryCollection, toggleLikedPaper, toggleSavedPaper, trackRecentPaper } from "@/lib/library";
import { ReportDialog } from "@/components/paper/ReportDialog";

interface PaperCardProps { paper: PaperSummary; }

const previewStyles = {
  math_heavy: { surface: "bg-[#f5e7c7]", ink: "text-[#7b531f]", rule: "bg-[#b9823d]", accent: "bg-[#d49434]" },
  diagram_heavy: { surface: "bg-[#f3e1d7]", ink: "text-[#814936]", rule: "bg-[#bc7658]", accent: "bg-[#d47d5e]" },
  text_only: { surface: "bg-[#e8eeee]", ink: "text-[#385d68]", rule: "bg-[#7899a1]", accent: "bg-[#5d8793]" },
  mixed: { surface: "bg-[#e6efde]", ink: "text-[#46633d]", rule: "bg-[#83a477]", accent: "bg-[#6d9561]" },
} as const;

const getPreviewStyle = (type?: PaperSummary["document_type"]) => previewStyles[type || "mixed"] || previewStyles.mixed;

const DocumentPreview: React.FC<{ paper: PaperSummary }> = ({ paper }) => {
  const [previewFailed, setPreviewFailed] = useState(false);
  const displayTitle = paper.title || paper.original_filename.replace(/\.[^/.]+$/, "");
  const style = getPreviewStyle(paper.document_type);
  const shortCode = (paper.course_code || "PAPER").slice(0, 10).toUpperCase();

  useEffect(() => setPreviewFailed(false), [paper.id]);

  return (
    <div className={`relative aspect-[0.78] overflow-hidden rounded-[9px] border border-black/5 ${previewFailed ? style.surface : "bg-[#eef1ed]"} transition-transform duration-200 group-hover:-translate-y-0.5`}>
      {!previewFailed ? (
        <img
          src={api.getPreviewUrl(paper.id)}
          alt={`${displayTitle} first page preview`}
          className="absolute inset-0 h-full w-full object-contain p-1.5"
          loading="lazy"
          onError={() => setPreviewFailed(true)}
        />
      ) : (
        <>
          <div className="flex items-center justify-between p-4 text-[8px] font-bold uppercase tracking-[0.13em] opacity-70"><span>Document</span><span>{paper.year || "24"}</span></div>
          <div className={`mx-4 mt-1 h-1 w-10 rounded-full ${style.accent}`} />
          <p className={`mt-3 px-4 text-[10px] font-semibold uppercase tracking-[0.14em] ${style.ink}`}>{shortCode}</p>
          <p className={`mt-2 line-clamp-3 px-4 text-[15px] font-semibold leading-[1.12] tracking-[-0.02em] ${style.ink}`}>{displayTitle}</p>
          <div className="mt-5 space-y-1.5 px-4 opacity-55"><span className={`block h-[3px] w-[88%] rounded-full ${style.rule}`} /><span className={`block h-[3px] w-[70%] rounded-full ${style.rule}`} /><span className={`block h-[3px] w-[81%] rounded-full ${style.rule}`} /></div>
          <div className={`absolute bottom-4 left-4 h-10 w-10 rounded-md border border-black/5 ${style.accent}/20`}><div className={`m-2 h-6 w-6 rounded-sm border-2 border-current opacity-45 ${style.ink}`} /></div>
          <div className={`absolute bottom-4 right-4 flex items-center gap-1 text-[9px] font-semibold uppercase tracking-[0.08em] ${style.ink}`}><FileText className="h-3 w-3" /> PDF</div>
        </>
      )}
      {paper.page_count ? <span className="absolute bottom-2 right-2 rounded bg-white/80 px-1.5 py-0.5 text-[9px] font-medium text-[#65706f] shadow-sm">{paper.page_count} pages</span> : null}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-[#1d2b31]/0 transition-colors group-hover:bg-[#1d2b31]/10"><span className="translate-y-1 rounded-md bg-white px-2.5 py-1.5 text-[11px] font-semibold text-[#30443b] opacity-0 shadow-sm transition-all group-hover:translate-y-0 group-hover:opacity-100">Open document</span></div>
    </div>
  );
};

export const PaperCard: React.FC<PaperCardProps> = ({ paper }) => {
  const [downloading, setDownloading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [liked, setLiked] = useState(false);
  const [saveCount, setSaveCount] = useState(paper.save_count || 0);
  const [moreOpen, setMoreOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [collectionName, setCollectionName] = useState("");
  const [collections, setCollections] = useState<LibraryCollection[]>([]);
  const [collectionMessage, setCollectionMessage] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const typeBadge = getDocumentTypeBadge(paper);
  const displayTitle = paper.title || paper.original_filename.replace(/\.[^/.]+$/, "");
  const context = useMemo(() => [paper.course_code, paper.course_name, paper.university].filter(Boolean).join(" · "), [paper.course_code, paper.course_name, paper.university]);

  useEffect(() => {
    setSaved(getSavedPaperIds().includes(paper.id));
    setLiked(getLikedPaperIds().includes(paper.id));
    setSaveCount(paper.save_count || 0);
    setCollections(getCollections());
  }, [paper.id]);

  useEffect(() => {
    if (!moreOpen) return;
    const positionMenu = () => {
      const button = moreButtonRef.current;
      if (!button) return;
      const rect = button.getBoundingClientRect();
      const width = 264;
      const minimumLeft = window.innerWidth >= 768 ? 264 : 12;
      const left = Math.min(Math.max(minimumLeft, rect.right - width), window.innerWidth - width - 12);
      const estimatedHeight = 330;
      const above = rect.top - estimatedHeight - 8;
      const top = above > 12 ? above : Math.min(window.innerHeight - estimatedHeight - 12, rect.bottom + 8);
      setMenuPosition({ top: Math.max(12, top), left });
    };
    positionMenu();
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, true);
    return () => {
      window.removeEventListener("resize", positionMenu);
      window.removeEventListener("scroll", positionMenu, true);
    };
  }, [moreOpen]);

  const handleDirectDownload = async (event: React.MouseEvent) => {
    event.preventDefault(); event.stopPropagation(); setDownloading(true);
    try { await api.triggerDirectDownload(paper.id, "refined", `${displayTitle}.pdf`); } finally { setTimeout(() => setDownloading(false), 1200); }
  };
  const handleSave = (event: React.MouseEvent) => {
    event.preventDefault(); event.stopPropagation();
    const nextSaved = toggleSavedPaper(paper.id);
    setSaved(nextSaved);
    setSaveCount((count) => Math.max(0, count + (nextSaved ? 1 : -1)));
    api.recordPaperInteraction(paper.id, nextSaved ? "save" : "unsave").then((result) => setSaveCount(result.save_count)).catch(() => undefined);
  };
  const handleLike = (event: React.MouseEvent) => {
    event.preventDefault(); event.stopPropagation();
    const nextLiked = toggleLikedPaper(paper.id);
    setLiked(nextLiked);
    api.recordPaperInteraction(paper.id, nextLiked ? "like" : "unlike").catch(() => undefined);
  };
  const handleMore = (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setMoreOpen((open) => !open);
    setCollectionMessage(null);
  };
  const handleDownloadFromMenu = async () => {
    setMoreOpen(false);
    setDownloading(true);
    try {
      const type = ["completed", "needs_review", "published"].includes(paper.status) ? "refined" : "original";
      await api.triggerDirectDownload(paper.id, type, `${displayTitle}.pdf`);
    } finally {
      setTimeout(() => setDownloading(false), 1200);
    }
  };
  const handleMoveToCollection = (name: string) => {
    const collection = addPaperToCollection(paper.id, name);
    if (!collection) return;
    setCollections(getCollections());
    setCollectionName("");
    setCollectionMessage(`Added to ${collection.name}`);
  };
  const openReport = () => {
    setMoreOpen(false);
    setReportOpen(true);
  };

  return (
    <article className="group min-w-0">
      <div className="relative rounded-xl border border-[#e2e7e3] bg-white p-2.5 paper-card-shadow transition-all duration-200 hover:-translate-y-0.5 hover:border-[#c6d8c1]">
        <Link href={`/papers/${paper.id}`} onClick={() => trackRecentPaper(paper.id)} className="block" aria-label={`Open ${displayTitle}`}><DocumentPreview paper={paper} /></Link>
        <div className="absolute right-4 top-4 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <button type="button" onClick={handleSave} aria-label={saved ? "Remove from saved" : "Save document"} className={`flex h-7 w-7 items-center justify-center rounded-md border shadow-sm backdrop-blur-sm transition-colors ${saved ? "border-[#b9d4ae] bg-[#edf7e9] text-[#3d843d]" : "border-white/80 bg-white/85 text-[#6e7b76] hover:text-[#3d843d]"}`}><Bookmark className="h-3.5 w-3.5" /></button>
          <button type="button" onClick={handleLike} aria-label={liked ? "Unlike document" : "Like document"} className={`flex h-7 w-7 items-center justify-center rounded-md border shadow-sm backdrop-blur-sm transition-colors ${liked ? "border-[#e7b7b0] bg-[#fff2ef] text-[#bd6759]" : "border-white/80 bg-white/85 text-[#6e7b76] hover:text-[#bd6759]"}`}><Heart className={`h-3.5 w-3.5 ${liked ? "fill-current" : ""}`} /></button>
        </div>
      </div>
      <div className="px-1 pt-3">
        <Link href={`/papers/${paper.id}`} onClick={() => trackRecentPaper(paper.id)} className="block"><h3 className="line-clamp-2 min-h-[36px] text-[13px] font-semibold leading-[1.35] text-[#223238] transition-colors group-hover:text-[#3e7c3e]">{displayTitle}</h3></Link>
        <p className="mt-1 line-clamp-1 text-[11px] font-medium text-[#6f7d77]">{context || "Academic document"}</p>
        <div className="mt-2 flex items-center justify-between gap-2"><span className={`truncate rounded px-1.5 py-1 text-[10px] font-medium ${typeBadge.bg} ${typeBadge.text}`}>{typeBadge.label}</span><span className="flex shrink-0 items-center gap-1 text-[10px] font-semibold text-[#65726d]">{paper.page_count ? `PDF · ${paper.page_count} ${paper.page_count === 1 ? "page" : "pages"}` : "PDF"}</span></div>
        <div className="relative mt-2 flex items-center justify-between border-t border-[#edf0ed] pt-2"><span className="flex items-center gap-2 text-[10px] font-medium text-[#6f7d77]"><span className="h-1.5 w-1.5 rounded-full bg-[#5aa34f]" /> PDF <span className="text-[#b0b9b4]">·</span> <Bookmark className="h-3 w-3" /> {saveCount} saved</span><button ref={moreButtonRef} type="button" onClick={handleMore} aria-label="More document actions" aria-expanded={moreOpen} className="rounded-md p-1 text-[#98a19f] hover:bg-[#f2f4f2] hover:text-[#55625d]"><MoreHorizontal className="h-3.5 w-3.5" /></button>
          {moreOpen && typeof document !== "undefined" ? createPortal(<><button type="button" aria-label="Close document actions" onClick={() => setMoreOpen(false)} className="fixed inset-0 z-[70] bg-transparent" /><div style={{ top: menuPosition.top, left: menuPosition.left }} onClick={(event) => event.stopPropagation()} className="fixed z-[75] w-64 border border-[#dfe6df] bg-white p-1.5 shadow-[0_12px_30px_rgba(35,53,43,0.15)]">
            <div className="flex items-center justify-between px-2.5 pb-1.5 pt-1"><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9aa39f]">Document actions</p><button type="button" onClick={() => setMoreOpen(false)} aria-label="Close document actions" className="rounded p-0.5 text-[#9aa39f] hover:bg-[#f1f4f0]"><X className="h-3.5 w-3.5" /></button></div>
            <button type="button" onClick={handleDownloadFromMenu} className="flex w-full items-center gap-2 px-2.5 py-2 text-left text-[12px] text-[#50615b] hover:bg-[#f4f7f3]"><Download className="h-3.5 w-3.5" /> Download PDF</button>
            <div className="my-1 border-t border-[#edf0ed]" />
            <p className="px-2.5 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9aa39f]">Move to collection</p>
            {collections.map((collection) => <button key={collection.name} type="button" onClick={() => handleMoveToCollection(collection.name)} className="block w-full truncate px-2.5 py-1.5 text-left text-[12px] text-[#50615b] hover:bg-[#f4f7f3]">{collection.name}</button>)}
            <form onSubmit={(event) => { event.preventDefault(); handleMoveToCollection(collectionName); }} className="mt-1 flex gap-1 px-2.5"><input value={collectionName} onChange={(event) => setCollectionName(event.target.value)} placeholder="New collection" className="min-w-0 flex-1 border border-[#dfe6df] px-2 py-1.5 text-[11px] outline-none focus:border-[#7ca575]" /><button type="submit" disabled={!collectionName.trim()} className="border border-[#cfe0cb] px-2 py-1.5 text-[11px] font-semibold text-[#4c7948] disabled:opacity-40">Add</button></form>
            {collectionMessage ? <p className="px-2.5 pt-1.5 text-[10px] text-[#4c8048]">{collectionMessage}</p> : null}
            <div className="my-1 border-t border-[#edf0ed]" />
            <button type="button" onClick={openReport} className="flex w-full items-center gap-2 px-2.5 py-2 text-left text-[12px] text-[#50615b] hover:bg-[#f4f7f3]">Report a problem</button>
          </div></>, document.body) : null}
          <ReportDialog paperId={paper.id} open={reportOpen} onClose={() => setReportOpen(false)} />
        </div>
      </div>
    </article>
  );
};
