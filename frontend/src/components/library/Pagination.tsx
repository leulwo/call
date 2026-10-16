"use client";

import React from "react";
import { ChevronLeft, ChevronRight } from "@/components/ui/icons";

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems: number;
  pageSize?: number;
}

export const Pagination: React.FC<PaginationProps> = ({ page, totalPages, onPageChange, totalItems, pageSize = 50 }) => {
  if (totalPages <= 1) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalItems);

  const baseClasses = "flex items-center gap-1 rounded-md border border-[#e1e6e1] bg-white px-2.5 py-1.5 text-[11px] font-medium text-[#55645e] transition-colors hover:border-[#bcd2b7] hover:text-[#3e7d40]";
  const disabledClasses = "cursor-not-allowed opacity-40 hover:border-[#e1e6e1] hover:text-[#55645e]";

  return (
    <div className="flex items-center justify-center gap-3 pt-6">
      <button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1} className={`${baseClasses} ${page <= 1 ? disabledClasses : ""}`} aria-label="Previous page">
        <ChevronLeft className="h-3.5 w-3.5" /> Prev
      </button>
      <span className="text-[11px] text-[#7d8985]">
        Page <span className="font-semibold text-[#314338]">{page}</span> of {totalPages}
        <span className="ml-2 hidden text-[#a0a8a6] sm:inline">({start}–{end} of {totalItems})</span>
      </span>
      <button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= totalPages} className={`${baseClasses} ${page >= totalPages ? disabledClasses : ""}`} aria-label="Next page">
        Next <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};
