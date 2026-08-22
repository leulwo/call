"use client";

import React, { useRef, useState } from "react";
import Image from "next/image";
import { AlertCircle, CheckCircle2 } from "@/components/ui/icons";
import { formatFileSize } from "@/lib/utils";

interface DropZoneProps { selectedFiles: File[]; onFilesSelect: (files: File[]) => void; error?: string | null; }

export const DropZone: React.FC<DropZoneProps> = ({ selectedFiles, onFilesSelect, error }) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const validateAndSet = (files: File[]) => {
    const validTypes = ["application/pdf", "image/png", "image/jpeg", "image/jpg", "image/tiff", "image/webp", "image/bmp"];
    if (files.some((file) => !validTypes.includes(file.type) && !file.name.match(/\.(pdf|png|jpe?g|tiff?|webp|bmp)$/i))) { alert("Please upload a PDF document or image file (PNG, JPG, TIFF)."); return; }
    if (files.length > 1 && files.some((file) => file.name.match(/\.pdf$/i))) { alert("Choose one PDF or multiple image pages."); return; }
    if (files.reduce((total, file) => total + file.size, 0) > 50 * 1024 * 1024) { alert("Files are too large. Maximum supported size is 50MB."); return; }
    onFilesSelect(files);
  };
  const handleDrop = (event: React.DragEvent) => { event.preventDefault(); setIsDragging(false); if (event.dataTransfer.files.length) validateAndSet(Array.from(event.dataTransfer.files)); };
  return <div className="w-full"><input ref={fileInputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.tiff,.webp,.bmp" multiple onChange={(event) => { if (event.target.files?.length) validateAndSet(Array.from(event.target.files)); }} className="hidden" /><div onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }} onDrop={handleDrop} onClick={() => fileInputRef.current?.click()} className={`relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-all sm:p-12 ${isDragging ? "scale-[1.01] border-amber-500 bg-amber-50/70" : selectedFiles.length ? "border-emerald-400 bg-emerald-50/30" : "border-stone-300/80 bg-white hover:border-amber-400 hover:bg-amber-50/20"} shadow-sm`}>
    {selectedFiles.length ? <div className="flex flex-col items-center space-y-3"><div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-800 shadow-sm"><CheckCircle2 className="h-8 w-8" /></div><div><p className="max-w-full truncate font-semibold text-stone-900 text-sm">{selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} image pages selected`}</p><p className="text-xs text-stone-500">{formatFileSize(selectedFiles.reduce((total, file) => total + file.size, 0))}</p></div><span className="mt-1 text-xs font-medium text-amber-700 underline">Click to choose different pages</span></div> : <div className="flex flex-col items-center space-y-4"><div className="relative mb-1 h-24 w-24"><Image src="/Upload-File--Streamline-Brooklyn.svg" alt="Upload document" fill className="object-contain" /></div><div className="space-y-1"><p className="text-base font-semibold text-stone-900">Drag & drop your document here, or <span className="text-amber-700 underline">browse files</span></p><p className="text-xs text-stone-500">Supports PDFs or multiple ordered phone scans (up to 50MB total)</p></div><div className="flex items-center gap-2 rounded-full border border-stone-200/80 bg-stone-100/80 px-3 py-1 text-[11px] font-medium text-stone-600"><span>PDF</span><span>•</span><span>PNG</span><span>•</span><span>JPG</span><span>•</span><span>TIFF</span></div></div>}
  </div>{error ? <div className="mt-3 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700"><AlertCircle className="h-4 w-4 shrink-0" /><span>{error}</span></div> : null}</div>;
};
