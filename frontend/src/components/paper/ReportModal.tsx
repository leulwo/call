"use client";

import React, { useState } from "react";
import { AlertTriangle, CheckCircle, X } from "@/components/ui/icons";
import { LottieIcon } from "@/components/ui/LottieIcon";
import { Button } from "@/components/ui/Button";

interface ReportModalProps {
  paperId: string;
}

export const ReportModal: React.FC<ReportModalProps> = ({ paperId }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedback.trim()) return;
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setIsOpen(false);
      setFeedback("");
    }, 2000);
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1 text-xs text-stone-600 hover:text-amber-800 transition-colors"
      >
        <AlertTriangle className="h-3.5 w-3.5" />
        <span>Report an inaccuracy in this paper</span>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/40 backdrop-blur-xs">
          <div className="relative w-full max-w-md rounded-xl bg-white p-6 shadow-xl border border-stone-200 animate-in fade-in zoom-in-95 duration-150">
            <button
              onClick={() => setIsOpen(false)}
              className="absolute top-4 right-4 p-1 text-stone-400 hover:text-stone-700 rounded-lg"
            >
              <X className="h-4 w-4" />
            </button>

            {submitted ? (
              <div className="text-center py-6 space-y-2">
                <CheckCircle className="h-12 w-12 text-emerald-600 mx-auto" />
                <h3 className="text-base font-bold text-stone-900">Feedback Submitted</h3>
                <p className="text-xs text-stone-500">
                  Thank you! Our pipeline will evaluate your note to regenerate a corrected version.
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-2 text-amber-800">
                  <LottieIcon
                    src="/wired-outline-1140-warning-triangle-hover-enlarge.json"
                    width={28}
                    height={28}
                  />
                  <h3 className="font-bold text-base text-stone-900">Report Inaccuracy</h3>
                </div>

                <p className="text-xs text-stone-500">
                  Notice an equation typo, missing negative sign, or formatting mistake? Describe it below:
                </p>

                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="e.g. In question 3, part (b), the denominator should be 2x instead of 2..."
                  rows={4}
                  required
                  className="w-full rounded-2xl border border-stone-200 p-3 text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20"
                />

                <div className="flex items-center justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setIsOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" size="sm">
                    Submit Report
                  </Button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
};
