"use client";

import React from "react";
import { LayoutGrid, List, Search, X } from "@/components/ui/icons";

interface SearchHeaderProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  selectedCategory: string;
  onSelectCategory: (cat: string) => void;
  viewMode: "grid" | "list";
  onToggleViewMode: (mode: "grid" | "list") => void;
  totalCount: number;
}

const CATEGORIES = [
  { id: "all", label: "Everything" },
  { id: "exam", label: "Exams" },
  { id: "study_notes", label: "Study notes" },
  { id: "assignment", label: "Assignments" },
  { id: "other", label: "Others" },
];

export const SearchHeader: React.FC<SearchHeaderProps> = ({ searchQuery, onSearchChange, selectedCategory, onSelectCategory, viewMode, onToggleViewMode, totalCount }) => {
  return (
    <div className="space-y-4">
      <div className="paper-search relative flex min-h-[58px] items-center rounded-lg border border-[#dce4dc] bg-white px-4 shadow-[0_3px_12px_rgba(42,62,47,0.05)] focus-within:border-[#75a16e] focus-within:ring-4 focus-within:ring-[#8fbe851c]">
        <Search className="h-[19px] w-[19px] shrink-0 text-[#6c8c6d]" />
        <input type="text" value={searchQuery} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search courses, documents, universities, exam papers..." className="w-full bg-transparent px-3 text-[14px] text-[#233339] outline-none placeholder:text-[#8d9999]" aria-label="Search the PaperFlow library" />
        {searchQuery ? <button type="button" onClick={() => onSearchChange("")} aria-label="Clear search" className="rounded-md p-1.5 text-[#8a9593] hover:bg-[#f0f3ef] hover:text-[#34423c]"><X className="h-4 w-4" /></button> : null}
        <span className="hidden border-l border-[#e5e9e5] pl-3 text-[11px] text-[#a0a8a6] sm:block">Try “CS201” or “past papers”</span>
      </div>

      <div className="flex flex-col justify-between gap-3 border-b border-[#e6e9e5] pb-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-2 overflow-x-auto no-scrollbar">
          {CATEGORIES.map((category) => <button key={category.id} type="button" onClick={() => onSelectCategory(category.id)} className={`shrink-0 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors ${selectedCategory === category.id ? "bg-[#e4f0de] text-[#376d3a]" : "text-[#6e7b78] hover:bg-[#f1f3ef] hover:text-[#30423a]"}`}>{category.label}</button>)}
        </div>
        <div className="flex shrink-0 items-center justify-between gap-3">
          <span className="text-[11px] text-[#88928f]">{totalCount} {totalCount === 1 ? "document" : "documents"}</span>
          <div className="flex items-center rounded-md border border-[#e1e6e1] bg-white p-0.5">
            <button type="button" onClick={() => onToggleViewMode("grid")} aria-label="Grid view" className={`rounded p-1.5 ${viewMode === "grid" ? "bg-[#edf4e9] text-[#3c7b3d]" : "text-[#909a97] hover:text-[#42514b]"}`}><LayoutGrid className="h-3.5 w-3.5" /></button>
            <button type="button" onClick={() => onToggleViewMode("list")} aria-label="List view" className={`rounded p-1.5 ${viewMode === "list" ? "bg-[#edf4e9] text-[#3c7b3d]" : "text-[#909a97] hover:text-[#42514b]"}`}><List className="h-3.5 w-3.5" /></button>
          </div>
        </div>
      </div>
    </div>
  );
};
