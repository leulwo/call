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

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [university, setUniversity] = useState("");
  const [universityType, setUniversityType] = useState("");
  const [studyYear, setStudyYear] = useState("");
  const [department, setDepartment] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [courseName, setCourseName] = useState("");
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [semester, setSemester] = useState("");
  const [examType, setExamType] = useState("");
  const [metadataNotes, setMetadataNotes] = useState("");
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
        university: university.trim() || null, university_type: universityType.trim() || null,
        study_year: studyYear.trim() || null, department: department.trim() || null,
        course_code: courseCode.trim() || null, course_name: courseName.trim() || null,
        year: year.trim() || null, semester: semester.trim() || null, exam_type: examType.trim() || null,
      };
      const metadataEnvelope = {
        schema_version: "paperflow.metadata.v1",
        context_query: metadataNotes.trim(),
        provided: providedMetadata,
        ui: { input_mode: "free_text", suggestions_are_optional: true },
      };
      const formData = new FormData();
      files.forEach((selectedFile) => formData.append("files", selectedFile));
      formData.append("title", title.trim());
      formData.append("description", description.trim());
      Object.entries({ university, university_type: universityType, study_year: studyYear, department, course_code: courseCode, course_name: courseName, year, semester, exam_type: examType }).forEach(([key, value]) => {
        if (value.trim()) formData.append(key, value.trim());
      });
      formData.append("metadata_json", JSON.stringify(metadataEnvelope));
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
    setFiles([]); setTitle(""); setDescription(""); setUniversity(""); setUniversityType(""); setStudyYear(""); setDepartment(""); setCourseCode(""); setCourseName("");
    setYear(new Date().getFullYear().toString()); setSemester(""); setExamType(""); setMetadataNotes(""); setEmail("");
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
      {uploading ? <ProgressTracker statusData={null} phase="uploading" /> : paperId && !showProgress ? <ThankYouCard paperId={paperId} email={email} mode={isCompleted ? "complete" : needsReview ? "needs_review" : "queued"} onContinue={isCompleted ? undefined : handleContinue} onReset={handleReset} /> : paperId && shouldShowProgress ? <ProgressTracker statusData={statusData} onReset={handleReset} /> : paperId ? <ThankYouCard paperId={paperId} email={email} mode={needsReview ? "needs_review" : "complete"} onContinue={needsReview ? handleContinue : undefined} onReset={handleReset} /> : (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-1"><h1 className="text-2xl font-bold tracking-tight text-stone-900 sm:text-3xl">Contribute a document</h1><p className="text-xs text-stone-500 sm:text-sm">Give the document a clear name and context. PaperFlow will refine the file and normalize the academic metadata after processing.</p></div>
          <DropZone selectedFiles={files} onFilesSelect={setFiles} error={error} />

          <div className="space-y-5 rounded-xl border border-stone-200/90 bg-white p-6 shadow-sm sm:p-8">
            <div><h2 className="text-sm font-bold text-stone-900">Document details</h2><p className="mt-1 text-[11px] leading-4 text-stone-500">These two fields are required so every library item has a useful identity before AI refinement begins.</p></div>
            <div className="space-y-4">
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Document name <span className="text-rose-600">*</span></span><input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. 2025 EmTe 1112 final examination" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Description <span className="text-rose-600">*</span></span><textarea required value={description} onChange={(event) => setDescription(event.target.value)} rows={3} placeholder="What is this document, who is it for, and what does it cover?" className={`${inputClass} resize-y leading-5`} /></label>
            </div>

            <div className="border-t border-stone-100 pt-5"><h2 className="text-sm font-bold text-stone-900">Academic metadata</h2><p className="mt-1 text-[11px] leading-4 text-stone-500">Everything below is free text. PaperFlow preserves what you enter, then normalizes it against document evidence and its metadata cache.</p></div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">University / institution</span><input value={university} onChange={(event) => setUniversity(event.target.value)} placeholder="Type any institution name or abbreviation" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">University type</span><input value={universityType} onChange={(event) => setUniversityType(event.target.value)} placeholder="e.g. public university" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Study year</span><input value={studyYear} onChange={(event) => setStudyYear(event.target.value)} placeholder="e.g. freshman, Year 2, graduate" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Department / program</span><input value={department} onChange={(event) => setDepartment(event.target.value)} placeholder="Type any department or program" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Course code</span><input value={courseCode} onChange={(event) => setCourseCode(event.target.value)} placeholder="Type a code such as emete1112" className={`${inputClass} font-mono`} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Course name</span><input value={courseName} onChange={(event) => setCourseName(event.target.value)} placeholder="Type the course name" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Document year</span><input value={year} onChange={(event) => setYear(event.target.value)} placeholder="e.g. 2025" className={inputClass} /></label>
              <label className="block space-y-1.5"><span className="text-xs font-semibold text-stone-700">Semester / exam term</span><input value={semester} onChange={(event) => setSemester(event.target.value)} placeholder="e.g. first semester, final" className={inputClass} /></label>
              <label className="block space-y-1.5 sm:col-span-2"><span className="text-xs font-semibold text-stone-700">Document type / assessment</span><input value={examType} onChange={(event) => setExamType(event.target.value)} placeholder="e.g. final exam, assignment, lecture notes, study guide" className={inputClass} /></label>
            </div>

            <div className="space-y-1.5 border-t border-stone-100 pt-5"><label className="text-xs font-semibold text-stone-700">Extra context for metadata mapping <span className="font-normal text-stone-500">(optional)</span></label><textarea value={metadataNotes} onChange={(event) => setMetadataNotes(event.target.value)} rows={3} placeholder="Example: The file says emete1112, but it is the Engineering Mathematics course for AASTU Year 1. Include abbreviations, faculty, campus, or alternate spellings here." className={`${inputClass} resize-y leading-5`} /><p className="text-[10px] leading-4 text-stone-500">After refinement, PaperFlow returns normalized metadata. Unknown values can be searched once, then reused from the cache on later uploads.</p></div>
            <div className="space-y-1.5 border-t border-stone-100 pt-5"><label className="text-xs font-semibold text-stone-700">Email notification <span className="font-normal text-stone-500">(optional)</span></label><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="student@example.com" className={inputClass} /></div>
          </div>

          <div className="flex items-center justify-end gap-3"><Link href="/"><Button type="button" variant="ghost" size="md">Cancel</Button></Link><Button type="submit" variant="primary" size="lg" disabled={!files.length || !title.trim() || !description.trim() || uploading} className="text-sm font-semibold shadow-sm" icon={<UploadCloud className="h-4 w-4" />}>{uploading ? "Uploading & queuing..." : "Upload & refine document"}</Button></div>
        </form>
      )}
    </div>
  );
}
