"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Search, University } from "@/components/ui/icons";
import { PaperSummary } from "@/lib/types";
import { api } from "@/lib/api";

export default function UniversitiesPage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [query, setQuery] = useState("");
  useEffect(() => { api.getPapers().then(setPapers).catch(console.error); }, []);
  const universities = useMemo(() => {
    const grouped = new Map<string, { count: number; type: string; years: Set<number> }>();
    papers.forEach((paper) => { const name = paper.university?.trim(); if (!name) return; const current = grouped.get(name) || { count: 0, type: paper.university_type || "", years: new Set<number>() }; current.count += 1; if (paper.university_type) current.type = paper.university_type; if (paper.year) current.years.add(paper.year); grouped.set(name, current); });
    return Array.from(grouped.entries()).map(([name, value]) => ({ name, ...value })).filter((value) => value.name.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [papers, query]);
  return <div className="space-y-8"><section className="border-b border-[#e6e9e5] pb-6"><p className="text-[11px] font-medium text-[#82908b]">Library / Universities</p><div className="mt-3 flex flex-col justify-between gap-4 lg:flex-row lg:items-end"><div><h1 className="text-[30px] font-bold tracking-[-0.04em] text-[#1f3035]">Universities represented in PaperFlow</h1><p className="mt-2 max-w-2xl text-[13px] leading-5 text-[#74807d]">This directory is generated only from document metadata. A university appears after a real uploaded document identifies it.</p></div><span className="text-[12px] text-[#899490]">{universities.length} represented</span></div></section><section className="border border-[#dfe7df] bg-white p-4"><label className="flex min-h-11 items-center gap-3 border border-[#dce4dc] px-3"><Search className="h-4 w-4 text-[#6c8c6d]" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a university from the document metadata..." className="min-w-0 flex-1 text-[13px] outline-none" /></label></section>{universities.length ? <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{universities.map((university) => <Link key={university.name} href={`/browse?university=${encodeURIComponent(university.name)}`} className="border border-[#e1e7e1] bg-white p-4 transition-colors hover:border-[#bcd2b7] hover:bg-[#f8fbf6]"><div className="flex items-start justify-between gap-4"><span className="flex h-9 w-9 items-center justify-center bg-[#e7f1e1] text-[#4d804c]"><University className="h-4 w-4" /></span><span className="text-[18px] text-[#a3afa9]">→</span></div><h2 className="mt-4 text-[14px] font-bold text-[#30423d]">{university.name}</h2><p className="mt-1 text-[11px] text-[#7f8b86]">{university.count} document{university.count === 1 ? "" : "s"}{university.type ? ` · ${university.type}` : ""}</p><p className="mt-2 text-[10px] text-[#9aa39f]">{Array.from(university.years).sort().join(" · ") || "Year not specified"}</p></Link>)}</div> : <div className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center text-[12px] text-[#7f8a87]">No university metadata has been published yet.</div>}</div>;
}
