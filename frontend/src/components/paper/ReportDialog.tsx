"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, X } from "@/components/ui/icons";
import { api } from "@/lib/api";

interface ReportDialogProps {
  paperId: string;
  open: boolean;
  onClose: () => void;
}

const REPORT_OPTIONS = [
  { value: "inaccurate metadata or content", label: "Inaccurate metadata or content" },
  { value: "abuse or request for removal", label: "Abuse or request for removal" },
  { value: "non-real, spam, or misleading document", label: "Non-real, spam, or misleading document" },
];

export const ReportDialog: React.FC<ReportDialogProps> = ({ paperId, open, onClose }) => {
  const [reason, setReason] = useState(REPORT_OPTIONS[0].value);
  const [details, setDetails] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setReason(REPORT_OPTIONS[0].value);
    setDetails("");
    setSubmitted(false);
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const submitReport = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await api.reportPaper(paperId, reason, details);
      setSubmitted(true);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not submit report.");
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Report document">
      <button type="button" aria-label="Close report dialog" onClick={onClose} className="absolute inset-0 bg-[#20302b]/40 backdrop-blur-[2px]" />
      <div onClick={(event) => event.stopPropagation()} className="relative z-10 w-full max-w-md border border-[#dfe6df] bg-white p-5 shadow-[0_20px_60px_rgba(28,43,35,0.22)]">
        <div className="flex items-start justify-between gap-4">
          <div><p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-[#70916d]"><AlertTriangle className="h-3.5 w-3.5" /> Moderation</p><h2 className="mt-1 text-[18px] font-semibold text-[#273936]">Report this document</h2></div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-[#82908b] hover:bg-[#f1f4f0]" aria-label="Close report"><X className="h-4 w-4" /></button>
        </div>
        {submitted ? <div className="mt-5 flex items-start gap-3 border border-[#cfe3c9] bg-[#f3faf0] p-4 text-[12px] leading-5 text-[#4c7548]"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /><span>{reason === "inaccurate metadata or content" ? "Thanks — the AI is regenerating this document right now, using your report as correction notes. A new version will appear shortly." : "Thanks — your report is being reviewed by our AI moderator. Clear violations are removed automatically; ambiguous ones go to a human."}</span></div> : <form onSubmit={submitReport} className="mt-5 space-y-4"><label className="block space-y-1.5"><span className="text-[11px] font-semibold text-[#53635d]">What is wrong?</span><select value={reason} onChange={(event) => setReason(event.target.value)} className="w-full border border-[#dfe6df] bg-white px-3 py-2.5 text-[12px] text-[#31423e] outline-none focus:border-[#7ca575]">{REPORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><textarea value={details} onChange={(event) => setDetails(event.target.value)} rows={4} placeholder="Add useful context (optional)" className="w-full resize-y border border-[#dfe6df] px-3 py-2.5 text-[12px] text-[#31423e] outline-none focus:border-[#7ca575]" /><p className="text-[10px] leading-4 text-[#8a9591]">{reason === "inaccurate metadata or content" ? "Tip: describe exactly what is wrong (wrong course code, missing question 5...) — your note becomes the AI's correction instructions." : "Explain why this document should be reviewed for removal."}</p>{error ? <p className="text-[11px] text-[#b85d53]">{error}</p> : null}<div className="flex justify-end gap-2"><button type="button" onClick={onClose} className="px-3 py-2 text-[12px] font-medium text-[#6d7974] hover:bg-[#f3f5f2]">Cancel</button><button type="submit" className="bg-[#3e8d3c] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#337733]">Send report</button></div></form>}
      </div>
    </div>
  );
};
