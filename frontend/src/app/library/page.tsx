"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bookmark, Clock3, Folder, Heart, Plus, RefreshCw, UploadCloud } from "@/components/ui/icons";
import { PaperCard } from "@/components/library/PaperCard";
import { PaperSummary } from "@/lib/types";
import { createCollection, getCollections, getGuestLibrarySnapshot, getLikedPaperIds, getProcessingPapers, getRecentPaperIds, getSavedPaperIds, getUploadedPaperIds, clearGuestLibraryData, hasGuestLibraryData, isGuestLibraryMigrated, markGuestLibraryMigrated, LibraryCollection, libraryChangeEvent, ProcessingPaperRecord } from "@/lib/library";
import { api, isAuthError } from "@/lib/api";
import { ProcessingStatusResponse } from "@/lib/types";
import { useAuth } from "@/components/auth/AuthProvider";

type LibraryTab = "uploads" | "saved" | "liked" | "recent" | "processing" | "collections";
const tabConfig: Array<{ id: LibraryTab; label: string; icon: React.ReactNode }> = [
  { id: "uploads", label: "My uploads", icon: <UploadCloud className="h-4 w-4" /> },
  { id: "saved", label: "Saved documents", icon: <Bookmark className="h-4 w-4" /> },
  { id: "liked", label: "Liked documents", icon: <Heart className="h-4 w-4" /> },
  { id: "recent", label: "Recently viewed", icon: <Clock3 className="h-4 w-4" /> },
  { id: "processing", label: "Processing uploads", icon: <RefreshCw className="h-4 w-4" /> },
  { id: "collections", label: "Collections", icon: <Folder className="h-4 w-4" /> },
];

export default function LibraryPage() {
  const { user, loading: authLoading, configured: authConfigured, signInWithGoogle } = useAuth();
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [myPapers, setMyPapers] = useState<PaperSummary[] | null>(null);
  const [cloudSaved, setCloudSaved] = useState<PaperSummary[] | null>(null);
  const [cloudLiked, setCloudLiked] = useState<PaperSummary[] | null>(null);
  const [cloudRecent, setCloudRecent] = useState<PaperSummary[] | null>(null);
  const [cloudCollections, setCloudCollections] = useState<Array<{ id: string; name: string; paperIds: string[] }> | null>(null);
  const [tab, setTab] = useState<LibraryTab>("uploads");
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [likedIds, setLikedIds] = useState<string[]>([]);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [uploadedIds, setUploadedIds] = useState<string[]>([]);
  const [collections, setCollections] = useState<LibraryCollection[]>([]);
  const [processingPapers, setProcessingPapers] = useState<ProcessingPaperRecord[]>([]);
  const [processingStatuses, setProcessingStatuses] = useState<Record<string, ProcessingStatusResponse>>({});
  const [selectedCollectionName, setSelectedCollectionName] = useState<string | null>(null);
  const [newCollectionName, setNewCollectionName] = useState("");

  const refreshLibrary = () => {
    setSavedIds(getSavedPaperIds());
    setLikedIds(getLikedPaperIds());
    setRecentIds(getRecentPaperIds());
    setUploadedIds(getUploadedPaperIds());
    setCollections(getCollections());
    setProcessingPapers(getProcessingPapers());
  };

  useEffect(() => {
    api.getPapers().then(setPapers).catch((error) => console.error("Failed to load library:", error));
    const queryTab = new URLSearchParams(window.location.search).get("tab") as LibraryTab | null;
    if (queryTab && tabConfig.some((item) => item.id === queryTab)) setTab(queryTab);
    refreshLibrary();
    window.addEventListener(libraryChangeEvent, refreshLibrary);
    return () => window.removeEventListener(libraryChangeEvent, refreshLibrary);
  }, []);

  // "My uploads" + cloud library come from the account, not localStorage.
  useEffect(() => {
    if (!user) {
      setMyPapers(null);
      setCloudSaved(null);
      setCloudLiked(null);
      setCloudRecent(null);
      setCloudCollections(null);
      return;
    }
    setMyPapers(null);
    api.getMyPapers().then(setMyPapers).catch((error) => {
      if (isAuthError(error)) { setMyPapers(null); return; }
      console.error("Failed to load your uploads:", error);
      setMyPapers([]);
    });
    api.getSavedPapers().then(setCloudSaved).catch(() => setCloudSaved([]));
    api.getLikedPapers().then(setCloudLiked).catch(() => setCloudLiked([]));
    api.getRecentPapers().then(setCloudRecent).catch(() => setCloudRecent([]));
    api.getCollections().then((result) => {
      setCloudCollections(result.map((item) => ({ id: item.id, name: item.name, paperIds: item.paper_ids })));
    }).catch(() => setCloudCollections([]));
  }, [user]);

  // Guest → account migration banner state
  const [migrationState, setMigrationState] = useState<"checking" | "offer" | "done" | "unavailable">("checking");
  const [migrating, setMigrating] = useState(false);
  useEffect(() => {
    if (!user) { setMigrationState("unavailable"); return; }
    if (isGuestLibraryMigrated() || !hasGuestLibraryData()) {
      setMigrationState("done");
      return;
    }
    setMigrationState("offer");
  }, [user]);

  const handleMigrate = async () => {
    setMigrating(true);
    try {
      const snapshot = getGuestLibrarySnapshot();
      await api.importGuestLibrary(snapshot);
      markGuestLibraryMigrated();
      clearGuestLibraryData();
      setMigrationState("done");
      refreshLibrary();
      if (user) {
        api.getSavedPapers().then(setCloudSaved).catch(() => undefined);
        api.getLikedPapers().then(setCloudLiked).catch(() => undefined);
        api.getRecentPapers().then(setCloudRecent).catch(() => undefined);
        api.getCollections().then((result) => setCloudCollections(result.map((item) => ({ id: item.id, name: item.name, paperIds: item.paper_ids })))).catch(() => undefined);
      }
    } catch (error) {
      console.error("Library import failed:", error);
    } finally {
      setMigrating(false);
    }
  };

  useEffect(() => {
    if (tab !== "processing" || !processingPapers.length) return;
    let cancelled = false;
    const fetchStatuses = () => {
      Promise.all(processingPapers.map(async (record) => {
        try { return [record.id, await api.getProcessingStatus(record.id)] as const; }
        catch { return null; }
      })).then((entries) => {
        if (cancelled) return;
        setProcessingStatuses(Object.fromEntries(entries.filter((entry): entry is readonly [string, ProcessingStatusResponse] => Boolean(entry))));
      });
    };
    fetchStatuses();
    const timer = window.setInterval(fetchStatuses, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [processingPapers, tab]);

  const idsForTab = tab === "uploads" ? uploadedIds : tab === "saved" ? savedIds : tab === "liked" ? likedIds : recentIds;
  const cloudListForTab = tab === "saved" ? cloudSaved : tab === "liked" ? cloudLiked : tab === "recent" ? cloudRecent : null;
  const selectedPapers = useMemo(() => {
    // Signed-in users read straight from the cloud lists (full paper objects,
    // works across devices even for papers outside the catalog's first page).
    if (user && cloudListForTab) return cloudListForTab;
    return idsForTab.map((id) => papers.find((paper) => paper.id === id)).filter((paper): paper is PaperSummary => Boolean(paper));
  }, [user, cloudListForTab, idsForTab, papers]);
  const activeCollections: Array<{ id?: string; name: string; paperIds: string[]; papers?: PaperSummary[] }> =
    user && cloudCollections ? cloudCollections : collections;
  const handleCreateCollection = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = newCollectionName.trim();
    if (!name) return;
    if (user) {
      try {
        const created = await api.createCollection(name);
        const result = await api.getCollections();
        setCloudCollections(result.map((item) => ({ id: item.id, name: item.name, paperIds: item.paper_ids, papers: item.papers })));
        setSelectedCollectionName(created.name);
        setNewCollectionName("");
      } catch (error) {
        console.error("Failed to create collection:", error);
      }
      return;
    }
    const collection = createCollection(name);
    if (collection) {
      setCollections(getCollections());
      setSelectedCollectionName(collection.name);
      setNewCollectionName("");
    }
  };
  const selectedCollection = activeCollections.find((collection) => collection.name === selectedCollectionName) || null;
  const collectionPapers: PaperSummary[] = selectedCollection
    ? selectedCollection.papers
      ? selectedCollection.papers
      : selectedCollection.paperIds.map((id) => papers.find((paper) => paper.id === id)).filter((paper): paper is PaperSummary => Boolean(paper))
    : [];

  return (
    <div className="space-y-8">
      {migrationState === "offer" ? (
        <section className="flex flex-col justify-between gap-3 rounded-xl border border-[#e3d9c8] bg-[#fffcf5] p-4 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-[13px] font-semibold text-[#5f4c33]">Bring your local library into your account?</h2>
            <p className="mt-0.5 text-[11px] leading-4 text-[#8a7a63]">We found saved documents, likes, history, and collections on this device from before you signed in. Merging copies them to your account so they follow you everywhere. Your local copies stay until the merge succeeds.</p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button type="button" onClick={handleMigrate} disabled={migrating} className="rounded-lg bg-[#3e8d3c] px-3.5 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-[#337733] disabled:opacity-50">{migrating ? "Merging..." : "Merge into account"}</button>
            <button type="button" onClick={() => { markGuestLibraryMigrated(); setMigrationState("done"); }} className="rounded-lg border border-[#e0d9cb] px-3.5 py-2 text-[12px] font-medium text-[#6b5543] hover:bg-[#f7f2e8]">Later</button>
          </div>
        </section>
      ) : null}
      <section className="border-b border-[#e6e9e5] pb-6">
        <p className="mb-3 text-[11px] font-medium text-[#82908b]">Library / Personal space</p>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div><h1 className="text-[30px] font-semibold tracking-[-0.04em] text-[#1f3035]">My library</h1><p className="mt-2 text-[13px] text-[#74807d]">Keep the documents worth another look close at hand.</p></div>
          <Link href="/upload" className="inline-flex w-fit items-center gap-2 rounded-lg bg-[#3e8d3c] px-3.5 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-[#337733]"><UploadCloud className="h-4 w-4" /> Add a document</Link>
        </div>
      </section>

      <div className="flex gap-1 overflow-x-auto border-b border-[#e6e9e5] no-scrollbar">
        {tabConfig.map((item) => <button key={item.id} type="button" onClick={() => setTab(item.id)} className={`flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-[12px] font-medium transition-colors ${tab === item.id ? "border-[#4b8b46] text-[#3d753e]" : "border-transparent text-[#7a8682] hover:text-[#41554a]"}`}>{item.icon}{item.label}</button>)}
      </div>

      {tab === "processing" ? (        processingPapers.length ? <section className="space-y-3">{processingPapers.map((record) => { const status = processingStatuses[record.id]; const done = status && ["completed", "needs_review", "published"].includes(status.status); const stage = status?.current_stage?.replace(/_/g, " ") || "queued"; const progress = status ? Math.min(status.current_stage_index || 0, status.total_stages || 6) : 0; const pending = !status; return <article key={record.id} className="border border-[#dfe7df] bg-white p-4 shadow-[0_3px_12px_rgba(42,62,47,0.04)]"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div className="min-w-0"><p className={`text-[10px] font-semibold uppercase tracking-[0.13em] ${pending ? "animate-pulse text-[#98a19f]" : "text-[#729171]"}`}>{done ? "Ready" : pending ? "Checking status…" : status?.status === "failed" ? "Needs attention" : "Still processing"}</p><h2 className="mt-1 truncate text-[14px] font-semibold text-[#2c3d3e]">{record.title}</h2><p className="mt-1 text-[11px] text-[#84908c]">{done ? "Processing finished." : pending ? "Fetching the latest progress…" : `Currently ${stage}. You can leave this page and come back anytime.`}</p></div><Link href={`/upload?paperId=${record.id}`} className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-[#cfe0cb] px-3 py-2 text-[11px] font-semibold text-[#4c7948] hover:bg-[#edf5ea]">View<span aria-hidden="true">→</span></Link></div>{pending ? <div className="mt-3 h-1.5 animate-pulse rounded-full bg-[#edf1eb]" /> : !done ? <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#edf1eb]"><div className="h-full rounded-full bg-[#5a9b54] transition-all" style={{ width: `${Math.max(8, (progress / Math.max(status?.total_stages || 6, 1)) * 100)}%` }} /></div> : null}</article>; })}</section> : <section className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center"><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-[#edf4e9] text-[#5d8c57]"><RefreshCw className="h-5 w-5" /></div><h2 className="mt-4 text-[16px] font-semibold text-[#2c3d3e]">No documents are processing</h2><p className="mx-auto mt-1 max-w-sm text-[12px] leading-5 text-[#7f8a87]">When you contribute a document, it will stay here so you can return while PaperFlow refines it.</p><Link href="/upload" className="mt-4 inline-flex items-center gap-2 text-[12px] font-semibold text-[#4b8248]">Upload a document <span aria-hidden="true">→</span></Link></section>
      ) : tab === "collections" ? (
        selectedCollection ? <section className="space-y-5"><div className="flex items-center justify-between border-b border-[#e6e9e5] pb-4"><div><button type="button" onClick={() => setSelectedCollectionName(null)} className="mb-2 inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#5d8060] hover:text-[#356d39]"><ArrowLeft className="h-3.5 w-3.5" /> All collections</button><h2 className="text-[22px] font-semibold tracking-[-0.03em] text-[#2c3d3e]">{selectedCollection.name}</h2><p className="mt-1 text-[12px] text-[#84908c]">{collectionPapers.length} {collectionPapers.length === 1 ? "document" : "documents"}</p></div><Folder className="h-6 w-6 text-[#5d8758]" /></div>{collectionPapers.length ? <section className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{collectionPapers.map((paper) => <PaperCard key={paper.id} paper={paper} />)}</section> : <section className="border border-dashed border-[#ccd8cc] bg-white px-5 py-14 text-center"><h3 className="text-[15px] font-semibold text-[#2c3d3e]">This collection is empty</h3><p className="mt-1 text-[12px] text-[#7f8a87]">Use a document&apos;s three-dot menu to move it here.</p><Link href="/" className="mt-4 inline-flex text-[12px] font-semibold text-[#4b8248]">Browse documents</Link></section>}</section> : <section className="space-y-4"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{activeCollections.map((collection, index) => <button key={collection.name} type="button" onClick={() => setSelectedCollectionName(collection.name)} className="group flex min-h-[126px] flex-col justify-between border border-[#e1e7e1] bg-white p-4 text-left transition-colors hover:border-[#bcd2b7]"><div className="flex items-start justify-between"><span className={`flex h-9 w-9 items-center justify-center rounded-md ${["bg-[#e8f1df]", "bg-[#f5ead7]", "bg-[#e6eef1]"][index % 3]} text-[#4b774b]`}><Folder className="h-4 w-4" /></span><span className="text-[11px] text-[#98a19f]">{collection.paperIds.length} documents</span></div><div><h2 className="text-[14px] font-semibold text-[#2c3d3e] group-hover:text-[#3d7e3d]">{collection.name}</h2><p className="mt-1 text-[11px] leading-4 text-[#84908c]">Personal document collection.</p></div></button>)}</div><form onSubmit={handleCreateCollection} className="flex max-w-md gap-2 border border-dashed border-[#c9d6c9] bg-[#fafcf9] p-3"><input value={newCollectionName} onChange={(event) => setNewCollectionName(event.target.value)} placeholder="Name a new collection" className="min-w-0 flex-1 bg-transparent px-2 text-[12px] outline-none" /><button type="submit" disabled={!newCollectionName.trim()} className="inline-flex items-center gap-1.5 rounded-md bg-[#3e8d3c] px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-40"><Plus className="h-3.5 w-3.5" /> Create</button></form>{!collections.length ? <p className="text-[12px] text-[#84908c]">Create a collection, then use the three-dot menu on any document to organize it.</p> : null}</section>
      ) : tab === "uploads" ? (
        !authConfigured ? (
          <section className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center"><h2 className="text-[16px] font-semibold text-[#2c3d3e]">Accounts are not enabled yet</h2><p className="mx-auto mt-1 max-w-sm text-[12px] leading-5 text-[#7f8a87]">Set NEXT_PUBLIC_SUPABASE_* in frontend/.env.local to enable sign-in.</p></section>
        ) : !user ? (
          <section className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center"><h2 className="text-[16px] font-semibold text-[#2c3d3e]">Sign in to see your uploads</h2><p className="mx-auto mt-1 max-w-sm text-[12px] leading-5 text-[#7f8a87]">Your contributions are tied to your Google account so they follow you across devices.</p><button type="button" onClick={() => signInWithGoogle("/library?tab=uploads")} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#3e8d3c] px-4 py-2.5 text-[12px] font-semibold text-white transition-colors hover:bg-[#337733]">Continue with Google</button></section>
        ) : myPapers === null ? (
          <div className="min-h-40 animate-pulse rounded-xl bg-[#eef1ed]" />
        ) : myPapers.length ? (
          <section className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{myPapers.map((paper) => <PaperCard key={paper.id} paper={paper} />)}</section>
        ) : (
          <section className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center"><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-[#edf4e9] text-[#5d8c57]"><UploadCloud className="h-5 w-5" /></div><h2 className="mt-4 text-[16px] font-semibold text-[#2c3d3e]">You haven&apos;t uploaded anything yet</h2><p className="mx-auto mt-1 max-w-sm text-[12px] leading-5 text-[#7f8a87]">Documents you contribute appear here, tied to your account.</p><Link href="/upload" className="mt-4 inline-flex items-center gap-2 text-[12px] font-semibold text-[#4b8248] hover:text-[#2f6835]">Upload a document <span aria-hidden="true">→</span></Link></section>
        )
      ) : selectedPapers.length ? (
        <section className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">{selectedPapers.map((paper) => <PaperCard key={paper.id} paper={paper} />)}</section>
      ) : (
        <section className="border border-dashed border-[#ccd8cc] bg-white px-5 py-16 text-center"><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-[#edf4e9] text-[#5d8c57]"><Bookmark className="h-5 w-5" /></div><h2 className="mt-4 text-[16px] font-semibold text-[#2c3d3e]">Nothing here yet</h2><p className="mx-auto mt-1 max-w-sm text-[12px] leading-5 text-[#7f8a87]">Save a document from the library and it will appear here, ready for your next study session.</p><Link href="/" className="mt-4 inline-flex items-center gap-2 text-[12px] font-semibold text-[#4b8248] hover:text-[#2f6835]">Explore the library <span aria-hidden="true">→</span></Link></section>
      )}
    </div>
  );
}
