"use client";

import React, { useEffect, useMemo, useState } from "react";
import { ArrowUpDown, LayoutGrid, List, Search, SlidersHorizontal } from "@/components/ui/icons";
import { PaperSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { PaperCard } from "@/components/library/PaperCard";
import { CompactListView } from "@/components/library/CompactListView";
import { Pagination } from "@/components/library/Pagination";
import { getCatalogDocumentCategory } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function BrowsePage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [query, setQuery] = useState("");
  const [university, setUniversity] = useState("all");
  const [year, setYear] = useState("all");
  const [type, setType] = useState("all");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(1);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("search")) setQuery(params.get("search") || "");
    if (params.get("university")) setUniversity(params.get("university") || "all");
  }, []);

  useEffect(() => {
    setPage(1);
  }, [query, university, year, type, sortOrder]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true);
      api.getPapers(query.trim() ? { search: query.trim() } : undefined)
        .then(setPapers)
        .catch(console.error)
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const universities = useMemo(
    () => Array.from(new Set(papers.map((paper) => paper.university).filter(Boolean))) as string[],
    [papers],
  );
  const years = useMemo(
    () => Array.from(new Set(papers.map((paper) => paper.year).filter((value): value is number => Boolean(value))))
      .sort((a, b) => Number(b) - Number(a)),
    [papers],
  );
  const filtered = useMemo(
    () => papers
      .filter((paper) => (
        (university === "all" || paper.university === university)
        && (year === "all" || String(paper.year) === year)
        && (type === "all" || getCatalogDocumentCategory(paper) === type)
      ))
      .sort((a, b) => {
        const dateA = a.created_at || "";
        const dateB = b.created_at || "";
        return sortOrder === "newest" ? dateB.localeCompare(dateA) : dateA.localeCompare(dateB);
      }),
    [papers, type, university, year, sortOrder],
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagePapers = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const hasActiveFilters = university !== "all" || year !== "all" || type !== "all";

  return (
    <div className="space-y-8">
      <section className="border-b border-[#e6e9e5] pb-6">
        <p className="text-[11px] font-medium text-[#82908b]">Library / Browse</p>
        <h1 className="mt-3 text-[30px] font-bold tracking-[-0.04em] text-[#1f3035]">Browse the document library</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-5 text-[#74807d]">Search the full collection, then narrow it by metadata that came from uploaded documents. Browse is for exploration; Home is your personalized shelf.</p>
      </section>

      <section className="border border-[#dfe7df] bg-white p-4">
        <div className="flex min-h-11 items-center gap-3 border border-[#dce4dc] px-3">
          <Search className="h-4 w-4 text-[#6c8c6d]" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search inside PDFs, courses, universities, and titles..." className="min-w-0 flex-1 text-[13px] outline-none" />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => setShowFilters((value) => !value)} aria-expanded={showFilters} aria-label="Toggle filters" title="Filters" className={`flex items-center border p-1 transition-colors ${showFilters || hasActiveFilters ? "border-[#bcd2b7] bg-[#edf4e9] text-[#3c7b3d]" : "border-transparent text-[#899490] hover:border-[#dfe6df] hover:text-[#55645e]"}`}>
            <SlidersHorizontal className="h-5 w-5" />
          </button>
          {showFilters && (
            <>
              <select value={university} onChange={(event) => setUniversity(event.target.value)} className="border border-[#dfe6df] px-2.5 py-2 text-[11px] text-[#4c5b56]"><option value="all">All universities</option>{universities.map((value) => <option key={value} value={value}>{value}</option>)}</select>
              <select value={year} onChange={(event) => setYear(event.target.value)} className="border border-[#dfe6df] px-2.5 py-2 text-[11px] text-[#4c5b56]"><option value="all">All years</option>{years.map((value) => <option key={value} value={String(value)}>{value}</option>)}</select>
              <select value={type} onChange={(event) => setType(event.target.value)} className="border border-[#dfe6df] px-2.5 py-2 text-[11px] text-[#4c5b56]"><option value="all">All categories</option><option value="exam">Exam</option><option value="study_notes">Study notes</option><option value="assignment">Assignment</option><option value="other">Others</option></select>
              <button type="button" onClick={() => setSortOrder(sortOrder === "newest" ? "oldest" : "newest")} aria-label={`Sorted by date, ${sortOrder} first. Click to switch.`} title={`Sorted by date — ${sortOrder === "newest" ? "newest" : "oldest"} first`} className="flex items-center gap-1.5 border border-[#dfe6df] bg-white px-2.5 py-2 text-[11px] font-medium text-[#55645e] transition-colors hover:border-[#bcd2b7] hover:text-[#3e7d40]">
                <ArrowUpDown className="h-3.5 w-3.5" />
                {sortOrder === "newest" ? "Newest" : "Oldest"}
              </button>
            </>
          )}
          <span className="ml-auto text-[11px] text-[#899490]">{filtered.length} documents</span>
          <div className="flex border border-[#e1e6e1] p-0.5">
            <button type="button" onClick={() => setView("grid")} className={`p-1.5 ${view === "grid" ? "bg-[#edf4e9] text-[#3c7b3d]" : "text-[#909a97]"}`} aria-label="Grid view"><LayoutGrid className="h-3.5 w-3.5" /></button>
            <button type="button" onClick={() => setView("list")} className={`p-1.5 ${view === "list" ? "bg-[#edf4e9] text-[#3c7b3d]" : "text-[#909a97]"}`} aria-label="List view"><List className="h-3.5 w-3.5" /></button>
          </div>
        </div>
      </section>

      {loading ? <div className="min-h-64 animate-pulse bg-[#eef1ed]" /> : <>
        {view === "grid"
          ? <div className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{pagePapers.map((paper) => <PaperCard key={paper.id} paper={paper} />)}</div>
          : <CompactListView papers={pagePapers} />}
        <Pagination page={safePage} totalPages={totalPages} onPageChange={setPage} totalItems={filtered.length} pageSize={PAGE_SIZE} />
      </>}
    </div>
  );
}
