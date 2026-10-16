"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, HelpCircle, Tag } from "@/components/ui/icons";
import { QuestionSchema } from "@/lib/types";

interface QuestionAccordionProps {
  questions: QuestionSchema[];
}

export const QuestionAccordion: React.FC<QuestionAccordionProps> = ({ questions }) => {
  const [expandedIndices, setExpandedIndices] = useState<number[]>([]);

  if (!questions || questions.length === 0) return null;

  const toggleQuestion = (index: number) => {
    setExpandedIndices((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
    );
  };

  return (
    <div className="space-y-4 border border-[#e1e7e1] bg-white p-5 shadow-[0_2px_8px_rgba(35,48,42,0.04)]">
      <div className="flex items-center justify-between border-b border-stone-100 pb-3">
        <div className="flex items-center gap-2">
          <HelpCircle className="h-5 w-5 text-amber-600" />
          <h2 className="text-base font-bold text-stone-900">Extracted Questions</h2>
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
            {questions.length}
          </span>
        </div>

        <button
          onClick={() =>
            setExpandedIndices(
              expandedIndices.length === questions.length ? [] : questions.map((_, i) => i)
            )
          }
          className="text-xs font-medium text-amber-700 hover:text-amber-900"
        >
          {expandedIndices.length === questions.length ? "Collapse All" : "Expand All"}
        </button>
      </div>

      <div className="divide-y divide-stone-100">
        {questions.map((q, idx) => {
          const isExpanded = expandedIndices.includes(idx);
          const num = q.display_number || `Q${idx + 1}`;

          return (
            <div key={q.id || idx} className="py-3">
              <button
                onClick={() => toggleQuestion(idx)}
                className="flex w-full items-start justify-between text-left gap-4 hover:text-amber-800 transition-colors"
              >
                <div className="flex items-start gap-2.5">
                  <span className="font-mono font-bold text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200 shrink-0">
                    {num}
                  </span>
                  <p className="text-xs font-medium text-stone-800 line-clamp-1">{q.text}</p>
                </div>

                <div className="flex items-center gap-2 shrink-0 text-xs text-stone-500">
                  {q.marks !== null && q.marks !== undefined && (
                    <span className="font-semibold text-stone-700">{q.marks} pts</span>
                  )}
                  {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </div>
              </button>

              {isExpanded && (
                <div className="mt-3 pl-8 space-y-2 text-xs text-stone-700">
                  <div className="p-3 bg-[#FAF7F2] rounded-xl border border-stone-200/80 font-mono whitespace-pre-wrap">
                    {q.text}
                  </div>

                  {q.topics && q.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {q.topics.map((t, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1 bg-stone-100 px-2 py-0.5 rounded-md text-[10px] text-stone-600 border border-stone-200"
                        >
                          <Tag className="h-2.5 w-2.5" />
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
