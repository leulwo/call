"use client";

import React, { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { BookOpen, FileText, GraduationCap, Layers, RefreshCw, UploadCloud } from "@/components/ui/icons";
import { PaperSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { getRecentPaperIds } from "@/lib/library";
import { SearchHeader } from "@/components/library/SearchHeader";
import { ShelfRow } from "@/components/library/ShelfRow";
import { PaperCard } from "@/components/library/PaperCard";
import { CompactListView } from "@/components/library/CompactListView";
import { Pagination } from "@/components/library/Pagination";
import { getCatalogDocumentCategory } from "@/lib/utils";

const CATALOG_PAGE_SIZE = 50;

const matchesCategory = (paper: PaperSummary, category: string) => {
  return category === "all" || getCatalogDocumentCategory(paper) === category;
};

const AnimatedStat: React.FC<{ value: number }> = ({ value }) => {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplayValue(value);
      return;
    }
    let frame = 0;
    const startedAt = performance.now();
    const duration = 720;
    const animate = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(Math.round(value * eased));
      if (progress < 1) frame = window.requestAnimationFrame(animate);
    };
    frame = window.requestAnimationFrame(animate);
    return () => window.cancelAnimationFrame(frame);
  }, [value]);

  return <>{displayValue.toLocaleString()}</>;
};

export default function HomePage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [catalogPage, setCatalogPage] = useState(1);

  const loadPapers = async (search?: string) => {
    setLoading(true);
    setLoadError(null);
    try { setPapers(await api.getPapers(search ? { search } : undefined)); }
    catch (error) {
      setLoadError(error instanceof TypeError
        ? "We couldn't connect to the document library. Please try again."
        : error instanceof Error ? error.message : "The document library couldn't be loaded.");
    }
    finally { setLoading(false); }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSearchQuery(params.get("q") || "");
    setRecentIds(getRecentPaperIds());
    loadPapers(params.get("q") || undefined);
  }, []);

  useEffect(() => {
    const query = searchQuery.trim();
    const timer = window.setTimeout(() => { if (query) loadPapers(query); else if (papers.length) loadPapers(); }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  useEffect(() => { setCatalogPage(1); }, [searchQuery, selectedCategory]);

  const filteredPapers = useMemo(() => {
    const byDate = [...papers].sort((a, b) => {
      const dateA = a.created_at || "";
      const dateB = b.created_at || "";
      return dateB.localeCompare(dateA);
    });
    return byDate.filter((paper) => selectedCategory === "all" || matchesCategory(paper, selectedCategory));
  }, [papers, selectedCategory]);
  const catalogTotalPages = Math.max(1, Math.ceil(filteredPapers.length / CATALOG_PAGE_SIZE));
  const catalogSafePage = Math.min(catalogPage, catalogTotalPages);
  const catalogPagePapers = filteredPapers.slice((catalogSafePage - 1) * CATALOG_PAGE_SIZE, catalogSafePage * CATALOG_PAGE_SIZE);
  const recentShelfPapers = useMemo(() => { const recent = recentIds.map((id) => papers.find((paper) => paper.id === id)).filter((paper): paper is PaperSummary => Boolean(paper)); return recent.length ? recent.slice(0, 6) : filteredPapers.slice(0, 6); }, [papers, recentIds, filteredPapers]);
  const popularPapers = useMemo(() => [...papers].sort((a, b) => (b.save_count || 0) - (a.save_count || 0) || (b.quality_score || 0) - (a.quality_score || 0)).slice(0, 6), [papers]);
  const examPapers = useMemo(() => filteredPapers.filter((paper) => getCatalogDocumentCategory(paper) === "exam").slice(0, 6), [filteredPapers]);
  const notesPapers = useMemo(() => filteredPapers.filter((paper) => getCatalogDocumentCategory(paper) === "study_notes").slice(0, 6), [filteredPapers]);
  const assignmentPapers = useMemo(() => filteredPapers.filter((paper) => getCatalogDocumentCategory(paper) === "assignment").slice(0, 6), [filteredPapers]);
  const universities = useMemo(() => Array.from(new Set(papers.map((paper) => paper.university).filter(Boolean))) as string[], [papers]);
  const courseCount = useMemo(() => new Set(papers.filter((paper) => paper.course_code || paper.course_name).map((paper) => `${paper.course_code || ""}:${paper.course_name || ""}`)).size, [papers]);
  const courseAreas = useMemo(() => {
    const colors = ["bg-[#e6eef1] text-[#426572]", "bg-[#f4ead4] text-[#84642f]", "bg-[#f0e3de] text-[#8b5444]", "bg-[#e6efdf] text-[#4f7848]", "bg-[#eee8f0] text-[#6e5e79]", "bg-[#f4e3e5] text-[#895766]"];
    const grouped = new Map<string, { label: string; code: string; count: number }>();
    papers.forEach((paper) => {
      const code = paper.course_code?.trim() || "";
      const name = paper.course_name?.trim() || "";
      if (!code && !name) return;
      const key = `${code.toLowerCase()}::${name.toLowerCase()}`;
      const existing = grouped.get(key);
      grouped.set(key, { label: name || code, code: code || name.slice(0, 5).toUpperCase(), count: (existing?.count || 0) + 1 });
    });
    return Array.from(grouped.values()).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)).slice(0, 6).map((area, index) => ({ ...area, color: colors[index % colors.length] }));
  }, [papers]);
  const showFilteredCatalog = Boolean(searchQuery.trim() || selectedCategory !== "all");

  return (
    <div className="space-y-8">
      <section className="library-intro flex flex-col justify-between gap-5 border-b border-[#e6e9e5] pb-6 lg:flex-row lg:items-end">
        <div>
          <div className="mb-3 flex items-center gap-2 text-[11px] font-medium text-[#82908b]"><span>Library</span><span>/</span><span className="text-[#4d7e4d]">Home</span></div>
          <h1 className="text-[28px] font-bold tracking-[-0.04em] text-[#1f3035] sm:text-[32px]">Find your next useful document.</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-5 text-[#74807d]">A focused academic library for exam papers, lecture notes, books, and study guides — organized around the way students actually study.</p>
        </div>
        <div className="catalog-ticket flex shrink-0 items-center self-start border border-[#e3e1d9] px-1 py-3 text-[11px] text-[#7d8985] lg:self-auto" aria-label="Library collection size">
          <div className="min-w-[78px] border-r border-[#e7e7df] px-3"><span className="block text-[20px] font-bold tracking-[-0.03em] text-[#314338]"><AnimatedStat value={papers.length} /></span><span>documents</span></div>
          <div className="min-w-[78px] border-r border-[#e7e7df] px-3"><span className="block text-[20px] font-bold tracking-[-0.03em] text-[#314338]"><AnimatedStat value={universities.length} /></span><span>universities</span></div>
          <div className="min-w-[78px] px-3"><span className="block text-[20px] font-bold tracking-[-0.03em] text-[#314338]"><AnimatedStat value={courseCount} /></span><span>courses</span></div>
        </div>
      </section>
      <SearchHeader searchQuery={searchQuery} onSearchChange={setSearchQuery} selectedCategory={selectedCategory} onSelectCategory={setSelectedCategory} viewMode={viewMode} onToggleViewMode={setViewMode} totalCount={filteredPapers.length} />
      {loading ? <div className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="animate-pulse"><div className="aspect-[0.78] rounded-xl bg-[#e8ece8]" /><div className="mt-3 h-3 w-4/5 rounded bg-[#e8ece8]" /><div className="mt-2 h-2 w-3/5 rounded bg-[#eef1ee]" /></div>)}</div> : loadError ? <div role="alert" className="flex min-h-[240px] flex-col items-center justify-center border border-[#e3e8e2] bg-white px-5 text-center"><h2 className="text-[17px] font-bold text-[#2a3a3a]">Couldn't load the library</h2><p className="mt-2 max-w-sm text-[13px] leading-5 text-[#74807d]">{loadError}</p><button type="button" onClick={() => loadPapers(searchQuery.trim() || undefined)} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#3e8d3c] px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-[#337733]"><RefreshCw className="h-4 w-4" />Try again</button></div> : filteredPapers.length === 0 ? <div className="flex min-h-[360px] flex-col items-center justify-center border border-dashed border-[#ccd8cc] bg-white px-5 text-center"><Image src="/Empty-Folder-E-Commerce--Streamline-Brooklyn.svg" alt="No documents found" width={90} height={90} className="mb-4 opacity-75" /><h2 className="text-[17px] font-bold text-[#2a3a3a]">No documents match that search</h2><p className="mt-1 max-w-sm text-[12px] leading-5 text-[#7f8a87]">Try a course code, university, subject, or a phrase from inside a document. You can also contribute the missing material.</p><Link href="/upload" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#3e8d3c] px-3.5 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-[#337733]"><UploadCloud className="h-4 w-4" /> Upload a document</Link></div> : showFilteredCatalog ? <section className="space-y-4"><div className="flex items-end justify-between border-b border-[#e6e9e5] pb-3"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#729171]">Library search</p><h2 className="mt-1 text-[19px] font-bold tracking-[-0.02em] text-[#25363a]">{searchQuery ? `Results for "${searchQuery}"` : "Filtered documents"}</h2></div><button type="button" onClick={() => loadPapers(searchQuery || undefined)} className="rounded-md p-2 text-[#87918e] hover:bg-[#f0f3ef] hover:text-[#3d6f3e]" aria-label="Refresh library"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button></div>{viewMode === "grid" ? <div className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{catalogPagePapers.map((paper) => <PaperCard key={paper.id} paper={paper} />)}</div> : <><CompactListView papers={catalogPagePapers} /><Pagination page={catalogSafePage} totalPages={catalogTotalPages} onPageChange={setCatalogPage} totalItems={filteredPapers.length} pageSize={CATALOG_PAGE_SIZE} /></>}</section> : <>
        {recentShelfPapers.length ? <ShelfRow title={recentIds.length ? "Continue reading" : "Recently added"} subtitle={recentIds.length ? "Pick up where you left off." : "Freshly refined papers and study material."} icon={<BookOpen className="h-[18px] w-[18px]" />} papers={recentShelfPapers} viewMode={viewMode} /> : null}
        {popularPapers.length ? <ShelfRow title="Popular in the library" subtitle="Useful documents with the strongest save activity." icon={<Layers className="h-[18px] w-[18px]" />} papers={popularPapers} viewMode={viewMode} /> : null}
        {examPapers.length ? <ShelfRow title="Exam papers" subtitle="Past papers, finals, and practice sets." icon={<FileText className="h-[18px] w-[18px]" />} papers={examPapers} viewMode={viewMode} /> : null}
        {notesPapers.length ? <ShelfRow title="Lecture notes & study guides" subtitle="Keep the concepts close before the next assessment." icon={<GraduationCap className="h-[18px] w-[18px]" />} papers={notesPapers} viewMode={viewMode} /> : null}
        {assignmentPapers.length ? <ShelfRow title="Assignments" subtitle="Coursework, problem sets, and submitted work." icon={<FileText className="h-[18px] w-[18px]" />} papers={assignmentPapers} viewMode={viewMode} /> : null}
        <section className="space-y-4 border-t border-[#e6e9e5] pt-7"><div className="flex items-end justify-between border-b border-[#e6e9e5] pb-3"><div className="flex items-center gap-2.5"><Image src="/Documents-1--Streamline-Brooklyn.svg" alt="" width={34} height={34} className="h-[34px] w-[34px] object-contain" /><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#729171]">Library collection</p><h2 className="mt-1 text-[19px] font-bold tracking-[-0.02em] text-[#25363a]">All documents</h2></div></div><span className="text-[11px] text-[#8c9793]">{filteredPapers.length} available</span></div>{viewMode === "grid" ? <div className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{catalogPagePapers.map((paper) => <PaperCard key={paper.id} paper={paper} />)}</div> : <><CompactListView papers={catalogPagePapers} /><Pagination page={catalogSafePage} totalPages={catalogTotalPages} onPageChange={setCatalogPage} totalItems={filteredPapers.length} pageSize={CATALOG_PAGE_SIZE} /></>}</section>
        <section className="space-y-4 border-t border-[#e6e9e5] pt-7"><div className="flex items-end justify-between"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#729171]">Browse the collection</p><h2 className="mt-1 text-[19px] font-bold tracking-[-0.02em] text-[#25363a]">Start with a course area</h2></div><Link href="/courses" className="text-[11px] font-semibold text-[#4c814b] hover:text-[#2f6835]">See all courses</Link></div>{courseAreas.length ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">{courseAreas.map((area) => <Link key={`${area.code}-${area.label}`} href={`/browse?search=${encodeURIComponent(`${area.code} ${area.label}`)}`} className="flex min-w-0 items-center gap-3 overflow-hidden border border-[#e3e8e2] bg-white p-3 text-left transition-colors hover:border-[#bcd2b7] hover:bg-[#f8fbf6]"><span className={`flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md px-1 text-center text-[9px] font-bold leading-3 ${area.color}`} title={area.code}>{area.code}</span><span className="min-w-0 flex-1 overflow-hidden"><span className="block truncate text-[12px] font-medium text-[#41514d]" title={area.label}>{area.label}</span><span className="mt-0.5 block truncate text-[10px] text-[#899490]">{area.count} {area.count === 1 ? "document" : "documents"}</span></span></Link>)}</div> : <p className="border border-dashed border-[#ccd8cc] bg-white px-4 py-5 text-[12px] text-[#7f8a87]">Course areas will appear here as documents contribute course metadata.</p>}</section>
        {universities.length ? <section className="space-y-3 border-t border-[#e6e9e5] pt-7"><div className="flex items-end justify-between"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#729171]">Academic directory</p><h2 className="mt-1 text-[19px] font-bold tracking-[-0.02em] text-[#25363a]">Browse by university</h2></div><Link href="/universities" className="text-[11px] font-semibold text-[#4c814b]">See all</Link></div><div className="flex flex-wrap gap-2">{universities.map((university) => <button key={university} type="button" onClick={() => setSearchQuery(university)} className="border border-[#e0e6e0] bg-white px-3 py-2 text-[12px] text-[#55645e] transition-colors hover:border-[#bcd2b7] hover:text-[#3e7d40]">{university}</button>)}</div></section> : null}
      </>}
    </div>
  );
}
