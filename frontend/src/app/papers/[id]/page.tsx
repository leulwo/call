"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2 } from "@/components/ui/icons";
import { PaperDetail } from "@/lib/types";
import { api } from "@/lib/api";
import { trackRecentPaper } from "@/lib/library";
import { PaperViewer } from "@/components/paper/PaperViewer";
import { useAuth } from "@/components/auth/AuthProvider";

export default function PaperDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const { user } = useAuth();
  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.getPaper(id).then((data) => { setPaper(data); trackRecentPaper(data.id); if (user) api.recordView(data.id); }).catch((err: Error) => setError(err.message || "Failed to load paper details")).finally(() => setLoading(false));
  }, [id, user]);

  return (
    <div className="mx-auto max-w-[1360px] space-y-5">
      <div className="flex items-center justify-between"><Link href="/" className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[#71807b] transition-colors hover:text-[#3f7c40]"><ArrowLeft className="h-4 w-4" /> Back to library</Link></div>
      {loading ? <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 text-center"><Loader2 className="h-7 w-7 animate-spin text-[#5b9256]" /><p className="text-[12px] text-[#7f8a87]">Opening the document reader...</p></div> : error || !paper ? <div className="mx-auto flex min-h-[320px] max-w-md flex-col items-center justify-center border border-dashed border-[#ccd8cc] bg-white px-6 text-center"><AlertCircle className="h-9 w-9 text-[#c76d5f]" /><h2 className="mt-3 text-[16px] font-semibold text-[#2d3f3f]">Document not found</h2><p className="mt-1 text-[12px] leading-5 text-[#818c89]">{error || "The requested document is not available in the library."}</p><Link href="/" className="mt-4 text-[12px] font-semibold text-[#4b8248]">Return to the library →</Link></div> : <PaperViewer paper={paper} />}
    </div>
  );
}
