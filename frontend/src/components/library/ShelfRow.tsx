"use client";

import React, { useRef } from "react";
import { ChevronLeft, ChevronRight } from "@/components/ui/icons";
import { PaperSummary } from "@/lib/types";
import { PaperCard } from "./PaperCard";
import { CompactListView } from "./CompactListView";

interface ShelfRowProps { title: string; subtitle?: string; icon?: React.ReactNode; papers: PaperSummary[]; viewMode?: "grid" | "list"; }

export const ShelfRow: React.FC<ShelfRowProps> = ({ title, subtitle, icon, papers, viewMode = "grid" }) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  if (papers.length === 0) return null;
  const handleScroll = (direction: "left" | "right") => scrollContainerRef.current?.scrollBy({ left: direction === "left" ? -520 : 520, behavior: "smooth" });

  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between gap-4">
        <div className="flex items-start gap-2">
          {icon ? <span className="mt-0.5 text-[#568c50]">{icon}</span> : null}
          <div><h2 className="text-[18px] font-semibold tracking-[-0.02em] text-[#25373a]">{title}</h2>{subtitle ? <p className="mt-0.5 text-[11px] text-[#899490]">{subtitle}</p> : null}</div>
        </div>
        {viewMode === "grid" ? <div className="flex items-center gap-2">
          <button type="button" onClick={() => handleScroll("left")} aria-label={`Scroll ${title} left`} className="flex h-7 w-7 items-center justify-center rounded-md border border-[#e1e7e1] bg-white text-[#71807b] transition-colors hover:border-[#bfd3bb] hover:text-[#3f7740]"><ChevronLeft className="h-4 w-4" /></button>
          <button type="button" onClick={() => handleScroll("right")} aria-label={`Scroll ${title} right`} className="flex h-7 w-7 items-center justify-center rounded-md border border-[#e1e7e1] bg-white text-[#71807b] transition-colors hover:border-[#bfd3bb] hover:text-[#3f7740]"><ChevronRight className="h-4 w-4" /></button>
        </div> : null}
      </div>
      {viewMode === "list" ? <CompactListView papers={papers} /> : <div ref={scrollContainerRef} className="-mx-1 flex snap-x snap-proximity gap-4 overflow-x-auto px-1 pb-2 pt-1 no-scrollbar scroll-smooth">
        {papers.map((paper) => <div key={paper.id} className="w-[184px] shrink-0 snap-start sm:w-[196px] lg:w-[208px]"><PaperCard paper={paper} /></div>)}
      </div>}
    </section>
  );
};
