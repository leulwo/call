"use client";

import React, { useEffect, useRef, useState } from "react";
import { UploadCloud, ArrowLeft } from "@/components/ui/icons";
import Link from "next/link";
import { DropZone } from "@/components/upload/DropZone";
import { ProgressTracker } from "@/components/upload/ProgressTracker";
import { ThankYouCard } from "@/components/upload/ThankYouCard";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { ProcessingStatusResponse } from "@/lib/types";
import { removeProcessingPaper, trackProcessingPaper, trackUploadedPaper } from "@/lib/library";
import { useAuth } from "@/components/auth/AuthProvider";

export default function UploadPage() {
  const { user, loading: authLoading, configured: authConfigured, signInWithGoogle } = useAuth();
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [university, setUniversity] = useState("");
  const [studyYear, setStudyYear] = useState("");
  const [department, setDepartment] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [courseName, setCourseName] = useState("");
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [examType, setExamType] = useState("");
  const [needsRefinement, setNeedsRefinement] = useState(true);
  const [email, setEmail] = useState("");

  const [uploading, setUploading] = useState(false);
  const [paperId, setPaperId] = useState<string | null>(null);
  const [statusData, setStatusData] = useState<ProcessingStatusResponse | null>(null);
  const [showProgress, setShowProgress] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const existingPaperId = new URLSearchParams(window.location.search).get("paperId");
    if (existingPaperId) {
      setPaperId(existingPaperId);
      setShowProgress(true);
    }
  }, []);

  useEffect(() => {
    if (!paperId) return;
    const poll = async () => {
      try {
        const data = await api.getProcessingStatus(paperId);
        setStatusData(data);
        if (["completed", "needs_review", "published"].includes(data.status)) removeProcessingPaper(paperId);
        if (["completed", "needs_review", "published", "failed"].includes(data.status) && pollingRef.current) clearInterval(pollingRef.current);
      } catch (pollError) {
        console.error("Polling error:", pollError);
      }
    };
    poll();
    pollingRef.current = setInterval(poll, 2500);
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [paperId]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!files.length) return setError("Please select a document to upload.");
    if (!title.trim()) return setError("A document name is required.");
    if (!description.trim()) return setError("A document description is required.");
    setError(null);
    setUploading(true);

    try {
      const providedMetadata = {
        title: title.trim(), description: description.trim(),
        university: university.trim() || null,
        study_year: studyYear.trim() || null, department: department.trim() || null,
        course_code: courseCode.trim() || null, course_name: courseName.trim() || null,
        year: year.trim() || null, exam_type: examType.trim() || null,
      };
      const metadataEnvelope = {
        schema_version: "paperflow.metadata.v1",
        provided: providedMetadata,
        ui: { input_mode: "free_text", suggestions_are_optional: true },
      };
      const formData = new FormData();
      files.forEach((selectedFile) => formData.append("files", selectedFile));
      formData.append("title", title.trim());
      formData.append("description", description.trim());
      Object.entries({ university, study_year: studyYear, department, course_code: courseCode, course_name: courseName, year, exam_type: examType }).forEach(([key, value]) => {
        if (value.trim()) formData.append(key, value.trim());
      });
      formData.append("metadata_json", JSON.stringify(metadataEnvelope));
      formData.append("needs_refinement", needsRefinement ? "true" : "false");
      if (email.trim()) formData.append("email", email.trim());
      const response = await api.uploadPaper(formData);
      setPaperId(response.id);
      trackUploadedPaper(response.id);
      trackProcessingPaper({ id: response.id, title: title.trim(), email: email.trim() || undefined, createdAt: new Date().toISOString() });
      setShowProgress(false);
      setUploading(false);
    } catch (submitError: any) {
      setError(submitError.message || "Failed to upload document. Please try again.");
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFiles([]); setTitle(""); setDescription(""); setUniversity(""); setStudyYear(""); setDepartment(""); setCourseCode(""); setCourseName("");
    setYear(new Date().getFullYear().toString()); setExamType(""); setNeedsRefinement(true); setEmail("");
    setPaperId(null); setStatusData(null); setShowProgress(false); setUploading(false); setError(null);
  };

  const handleContinue = async () => {
    if (!paperId) return;
    if (statusData?.status === "needs_review") {
      setError(null);
      try {
        await api.reprocessPaper(paperId);
        setStatusData(null);
      } catch (reprocessError: any) {
        setError(reprocessError.message || "Could not restart refinement.");
        return;
      }
    }
    setShowProgress(true);
  };

  const isCompleted = Boolean(statusData && ["completed", "published"].includes(statusData.status));
  const needsReview = statusData?.status === "needs_review";
  const inputClass = "w-full rounded-xl border border-stone-200 px-3 py-2.5 text-sm text-stone-900 outline-none transition placeholder:text-stone-400 focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20";

  const shouldShowProgress = Boolean(paperId && showProgress && !isCompleted && !needsReview);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link href="/" className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-600 transition-colors hover:text-stone-900"><ArrowLeft className="h-4 w-4" /><span>Back to Library</span></Link>
      {authLoading ? (
        <div className="flex min-h-[40vh] items-center justify-center text-sm text-stone-500">Checking your session...</div>
      ) : !user ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center rounded-xl border border-stone-200/90 bg-white p-10 text-center shadow-sm">
          <h1 className="text-xl font-bold text-stone-900">Sign in to contribute</h1>
          <p className="mt-2 max-w-sm text-[13px] leading-5 text-stone-500">Uploading is tied to a Google account so the library knows who contributed each document. Browsing and searching stay open to everyone.</p>
          <button
            type="button"
            onClick={() => signInWithGoogle("/upload")}
            disabled={!authConfigured}
            className="mt-5 flex items-center gap-2.5 rounded-xl bg-[#3e8d3c] px-5 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[#337733] disabled:opacity-50"
          >
            <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" aria-hidden="true"><path fill="currentColor" d="M21.35 11.1H12v3.8h5.35c-.5 2.4-2.6 3.8-5.35 3.8a5.9 5.9 0 1 1 0-11.8c1.5 0 2.85.55 3.9 1.45l2.8-2.8A9.9 9.9 0 0 0 12 2a10 10 0 1 0 0 20c5.75 0 9.55-4.05 9.55-9.75 0-.4-.05-.8-.2-1.15Z"/></svg>
            Continue with Google
          </button>
          {!authConfigured ? <p className="mt-3 text-[11px] text-stone-400">Auth is not configured yet (frontend/.env.local)</p> : null}
        </div>
      ) : uploading ? <ProgressTracker statusData={null} phase="uploading" /> : paperId && !showProgress ? <ThankYouCard paperId={paperId} email={email} mode={isCompleted ? "complete" : needsReview ? "needs_review" : "queued"} onContinue={isCompleted ? undefined : handleContinue} onReset={handleReset} /> : paperId && shouldShowProgress ? <ProgressTracker statusData={statusData} onReset={handleReset} /> : paperId ? <ThankYouCard paperId={paperId} email={email} mode={needsReview ? "needs_review" : "complete"} onContinue={needsReview ? handleContinue : undefined} onReset={handleReset} /> : (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-1"><h1 className="text-2xl font-bold tracking-tight text-stone-900 sm:text-3xl">Contribute a document</h1><p className="text-xs text-stone-500 sm:text-sm">Give the document a clear name and context. PaperFlow will refine the file and normalize the academic metadata after processing.</p></div>
          <DropZone selectedFiles={files} onFilesSelect={setFiles} error={error} />

          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-stone-200/90 bg-white p-4 shadow-sm transition-colors hover:border-stone-300">
            <input type="checkbox" checked={needsRefinement} onChange={(event) => setNeedsRefinement(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#3e8d3c]" />
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-stone-700">Needs refinement</span>
              <span className="mt-0.5 block text-[11px] leading-4 text-stone-500">PaperFlow will clean the pages, extract the text, and rebuild a readable PDF. Limited to 30 pages per document and 90 pages per day. If your file is already clean and final, uncheck this to publish it as-is.</span>
            </span>
          </label>

          <div className="space-y-5 rounded-xl border border-stone-200/90 bg-white p-6 shadow-sm sm:p-8">
            <div><h2 className="text-sm font-bold text-stone-900">Document details</h2><p className="mt-1 text-[11px] leading-4 text-stone-500">These two fields are required so every library item has a useful identity before AI refinement begins.</p></div>
            <div className="space-y-4">
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Document name <span className="text-rose-600">*</span></span><input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. 2025 EmTe 1112 final examination" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Description <span className="text-rose-600">*</span></span><textarea required value={description} onChange={(event) => setDescription(event.target.value)} rows={3} placeholder="What is this document, who is it for, and what does it cover?" className={`${inputClass} resize-y leading-5`} /></label>
            </div>

            <div className="border-t border-stone-100 pt-5"><h2 className="text-sm font-bold text-stone-900">Academic metadata</h2><p className="mt-1 text-[11px] leading-4 text-stone-500">Everything below is free text. PaperFlow preserves what you enter, then normalizes it against document evidence and its metadata cache.</p></div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">University / institution</span><input value={university} onChange={(event) => setUniversity(event.target.value)} placeholder="Type any institution name or abbreviation" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Study year</span><input value={studyYear} onChange={(event) => setStudyYear(event.target.value)} placeholder="e.g. freshman, Year 2, graduate" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Department / program</span><input value={department} onChange={(event) => setDepartment(event.target.value)} placeholder="Type any department or program" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Course code</span><input value={courseCode} onChange={(event) => setCourseCode(event.target.value)} placeholder="Type a code such as emete1112" className={`${inputClass} font-mono`} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Course name</span><input value={courseName} onChange={(event) => setCourseName(event.target.value)} placeholder="Type the course name" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Document year</span><input value={year} onChange={(event) => setYear(event.target.value)} placeholder="e.g. 2025" className={inputClass} /></label>
              <label className="block space-y-1.5 sm:col-span-2"><span className="text-xs font-semibold text-stone-700">Document type / assessment</span><input value={examType} onChange={(event) => setExamType(event.target.value)} placeholder="e.g. final exam, assignment, lecture notes, study guide" className={inputClass} /></label>
            </div>

            <div className="space-y-1.5 border-t border-stone-100 pt-5"><label className="text-xs font-semibold text-stone-700">Email notification <span className="font-normal text-stone-500">(optional)</span></label><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="student@example.com" className={inputClass} /></div>
          </div>

          <div className="flex items-center justify-end gap-3"><Link href="/"><Button type="button" variant="ghost" size="md">Cancel</Button></Link><Button type="submit" variant="primary" size="lg" disabled={!files.length || !title.trim() || !description.trim() || uploading} className="text-sm font-semibold shadow-sm" icon={<UploadCloud className="h-4 w-4" />}>{uploading ? "Uploading & queuing..." : "Upload & refine document"}</Button></div>
        </form>
      )}
    </div>
  );
}
