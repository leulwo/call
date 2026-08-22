"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "@/components/ui/icons";
import { ProcessingStatusResponse } from "@/lib/types";

interface ProgressTrackerProps { statusData: ProcessingStatusResponse | null; onReset?: () => void; phase?: "uploading" | "processing"; }

const STAGES = [
  { key: "queued", label: "Starting the refinement pipeline", desc: "Your upload is complete. PaperFlow is getting the document ready.", asset: "/uploadupload.svg" },
  { key: "preprocess", label: "Cleaning the pages", desc: "Straightening scans and preparing readable pages.", asset: "/preprocesupload.svg" },
  { key: "extract", label: "Reading the document", desc: "Finding text, equations, and page structure.", asset: "/extractupload.svg" },
  { key: "analyze", label: "Understanding the material", desc: "Organizing course metadata and document structure.", asset: "/analyzeupload.svg" },
  { key: "rewrite", label: "Preparing the readable version", desc: "Formatting the document for a clear study experience.", asset: "/rewriteupload.svg" },
  { key: "render", label: "Finalizing your document", desc: "Packaging the PDF and checking the result.", asset: "/renderdocumentupload.svg" },
  { key: "store", label: "Saving it to the library", desc: "Making the document available in PaperFlow.", asset: "/renderdocumentupload.svg" },
];

export const ProgressTracker: React.FC<ProgressTrackerProps> = ({ statusData, onReset, phase = "processing" }) => {
  const isUploading = phase === "uploading";
  const runningStage = statusData?.stages.find((stage) => stage.status === "running")?.name;
  const currentStageName = runningStage || statusData?.failed_stage || statusData?.current_stage || "queued";
  const stage = STAGES.find((item) => item.key === currentStageName) || STAGES[0];
  const isFailed = statusData?.status === "failed";
  const isQueued = !isUploading && currentStageName === "queued";

  return <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center py-4">
    <section className="w-full max-w-2xl border border-[#dfe7df] bg-white px-6 py-8 shadow-[0_8px_26px_rgba(36,55,42,0.06)] sm:px-12 sm:py-10">
      <div className="mb-6 flex items-center"><Link href="/" className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#66836a] hover:text-[#356d39]"><ArrowLeft className="h-3.5 w-3.5" /> Back to library</Link></div>
      <div className="text-center">
        <div className="paperflow-stage-art-shell mx-auto mb-6 flex h-40 w-40 items-center justify-center rounded-full bg-[#f0f6ec] sm:h-48 sm:w-48"><img key={stage.asset} src={stage.asset} alt="" className="paperflow-stage-art h-32 w-32 object-contain sm:h-40 sm:w-40" /></div>
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#6c9169]">{isUploading ? "Upload in progress" : isFailed ? "Upload paused" : isQueued ? "Getting ready" : `Step ${Math.min(statusData?.current_stage_index || 1, 6)} of 6`}</p>
        <h1 className="mt-2 text-[26px] font-bold tracking-[-0.03em] text-[#243835] sm:text-[30px]">{isUploading ? "Uploading your document" : isFailed ? "We couldn’t finish this upload" : stage.label}</h1>
        <p className="mx-auto mt-2 max-w-md text-[13px] leading-5 text-[#7a8881]">{isUploading ? "Sending your file securely to PaperFlow. This will only take a moment." : isFailed ? statusData?.error || "The source document is still safe. You can return to the library and try again." : stage.desc}</p>
      </div>
      <div className="mt-8 flex items-center justify-center gap-2 border-t border-[#eef1ee] pt-5 text-[11px] text-[#7b8982]">{isFailed ? <><span className="font-semibold text-[#a9655b]">Needs attention</span>{onReset ? <button type="button" onClick={onReset} className="font-semibold text-[#4b8049] hover:underline">Start over</button> : null}</> : <><Loader2 className="h-3.5 w-3.5 animate-spin text-[#4e954d]" /><span>{isUploading ? "Preparing the processing queue..." : "PaperFlow is working on your document."}</span></>}</div>
    </section>
  </div>;
};
