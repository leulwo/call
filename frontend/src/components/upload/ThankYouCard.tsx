"use client";

import React, { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Download, CheckCircle2, Eye, PlusCircle, Mail, ArrowRight, ArrowLeft } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";

interface ThankYouCardProps {
  paperId: string;
  email?: string;
  onReset: () => void;
  onContinue?: () => void;
  mode?: "queued" | "needs_review" | "complete";
}

export const ThankYouCard: React.FC<ThankYouCardProps> = ({ paperId, email, onReset, onContinue, mode = "complete" }) => {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const isQueued = mode === "queued";
  const needsReview = mode === "needs_review";

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await api.triggerDirectDownload(paperId, "refined", `paper-${paperId}-refined.pdf`);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Download failed. Please try again.");
    } finally {
      setTimeout(() => setDownloading(false), 1200);
    }
  };

  return (
    <div className="w-full rounded-xl border border-[#e1e7e1] bg-white p-8 sm:p-12 text-center shadow-lg space-y-6 max-w-xl mx-auto">
      {/* Streamline Illustration from public/ */}
      <div className="relative h-32 w-32 mx-auto">
        <Image
          src="/Thank-You-2--Streamline-Brooklyn.svg"
          alt="Thank you for contributing"
          fill
          className="object-contain"
          priority
        />
      </div>

      <div className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#6c9169]">{isQueued ? "Thank you" : needsReview ? "Processing needs attention" : "Ready for study"}</p>
        <h2 className="text-2xl font-bold tracking-tight text-stone-900 sm:text-3xl">{isQueued ? "Thank you for contributing." : needsReview ? "We couldn’t finish the automatic cleanup." : "Your document is ready."}</h2>
        <p className="mx-auto max-w-md text-sm leading-relaxed text-stone-600">{isQueued ? "Thank you for contributing. Your document is safely in the processing queue. You can now close this page, or continue to watch the refinement." : needsReview ? "Your uploaded document is safe, but PaperFlow could not finish the AI refinement. A cleaned preview is available. You can try again or return to the library." : "The document has finished processing and is now available as a readable PDF."}</p>
        {email?.trim() ? <p className="mx-auto flex max-w-md items-center justify-center gap-1.5 text-xs font-medium text-[#4c8048]"><Mail className="h-3.5 w-3.5" />We’ll notify {email.trim()} when it is ready.</p> : null}
      </div>

      {downloadError ? <p className="text-[12px] font-medium text-[#a9655b]">{downloadError}</p> : null}
      <div className="flex flex-col items-center justify-center gap-3 pt-2 sm:flex-row">
        {isQueued || needsReview ? <><Link href="/library?tab=processing" className="w-full sm:w-auto"><Button variant="outline" size="lg" className="w-full sm:w-auto" icon={<ArrowLeft className="h-4 w-4" />}>Return to library</Button></Link>{onContinue ? <Button onClick={onContinue} variant="primary" size="lg" className="w-full text-base font-semibold shadow-md hover:shadow-lg sm:w-auto" icon={<ArrowRight className="h-4 w-4" />}>{needsReview ? "Retry automatic cleanup" : "Continue processing"}</Button> : null}</> : <><Button onClick={handleDownload} variant="primary" size="lg" className="w-full text-base font-semibold shadow-md hover:shadow-lg sm:w-auto" icon={downloading ? <CheckCircle2 className="h-5 w-5 animate-spin" /> : <Download className="h-5 w-5" />}>{downloading ? "Downloading PDF..." : "Download PDF"}</Button><Link href={`/papers/${paperId}`} className="w-full sm:w-auto"><Button variant="outline" size="lg" className="w-full sm:w-auto" icon={<Eye className="h-4 w-4" />}>View document</Button></Link></>}
      </div>

      {!isQueued ? <div className="border-t border-stone-100 pt-4">
        <button
          onClick={onReset}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 transition-colors hover:text-amber-800"
        >
          <PlusCircle className="h-3.5 w-3.5" />
          <span>Upload another document</span>
        </button>
      </div> : null}
    </div>
  );
};
