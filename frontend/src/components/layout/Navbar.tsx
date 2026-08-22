"use client";

import React, { FormEvent, useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  BookOpen,
  Bookmark,
  Clock3,
  Folder,
  GraduationCap,
  Heart,
  Home,
  Layers,
  Menu,
  Search,
  University,
  UploadCloud,
} from "@/components/ui/icons";

type NavItem = { label: string; href: string; icon: React.ReactNode; exact?: boolean };

const primaryItems: NavItem[] = [
  { label: "Home", href: "/", icon: <Home className="h-4 w-4" />, exact: true },
  { label: "Browse", href: "/browse", icon: <Layers className="h-4 w-4" /> },
  { label: "My library", href: "/library", icon: <BookOpen className="h-4 w-4" /> },
  { label: "Recently viewed", href: "/library?tab=recent", icon: <Clock3 className="h-4 w-4" /> },
  { label: "Processing uploads", href: "/library?tab=processing", icon: <UploadCloud className="h-4 w-4" /> },
];

const savedItems: NavItem[] = [
  { label: "Saved", href: "/library?tab=saved", icon: <Bookmark className="h-4 w-4" /> },
  { label: "Liked", href: "/library?tab=liked", icon: <Heart className="h-4 w-4" /> },
  { label: "Collections", href: "/library?tab=collections", icon: <Folder className="h-4 w-4" /> },
];

const exploreItems: NavItem[] = [
  { label: "Universities", href: "/universities", icon: <University className="h-4 w-4" /> },
  { label: "Courses & subjects", href: "/courses", icon: <GraduationCap className="h-4 w-4" /> },
];

const isActive = (pathname: string, searchParams: { get: (name: string) => string | null }, item: NavItem) => {
  const [hrefPath, hrefQuery = ""] = item.href.split("?");
  const expected = new URLSearchParams(hrefQuery);

  if (hrefPath === "/") {
    if (expected.has("view")) return pathname === "/" && searchParams.get("view") === expected.get("view");
    return pathname === "/" && !searchParams.get("view");
  }

  if (hrefPath === "/library") {
    if (expected.has("tab")) return pathname === "/library" && searchParams.get("tab") === expected.get("tab");
    return pathname === "/library" && !searchParams.get("tab");
  }

  return pathname === hrefPath || pathname.startsWith(`${hrefPath}/`);
};

export const Navbar: React.FC = () => {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = query.trim();
    router.push(value ? `/?q=${encodeURIComponent(value)}` : "/");
    setMobileOpen(false);
  };

  const renderItems = (items: NavItem[]) => items.map((item) => (
    <Link
      key={item.label}
      href={item.href}
      onClick={() => setMobileOpen(false)}
      className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors ${
        isActive(pathname, searchParams, item)
          ? "bg-[#e8f1df] font-semibold text-[#345c34]"
          : "text-[#58636d] hover:bg-[#f1f3ef] hover:text-[#1d2b31]"
      }`}
    >
      <span className={isActive(pathname, searchParams, item) ? "text-[#4b8b42]" : "text-[#7e8990] group-hover:text-[#4b8b42]"}>{item.icon}</span>
      <span>{item.label}</span>
    </Link>
  ));

  return (
    <>
      <header className="fixed inset-x-0 top-0 z-40 h-16 border-b border-[#e5e8e4] bg-white/95 backdrop-blur-sm">
        <div className="flex h-full items-center gap-3 px-4 md:pl-7 md:pr-6">
          <button
            type="button"
            aria-label="Toggle navigation"
            onClick={() => setMobileOpen((value) => !value)}
            className="rounded-lg p-2 text-[#667279] hover:bg-[#f1f3ef] md:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link href="/" className="flex shrink-0 items-center gap-2.5" onClick={() => setMobileOpen(false)}>
            <span className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-[10px] bg-[#365f39] shadow-[0_3px_8px_rgba(46,87,49,0.16)]">
              <Image src="/Logo.png" alt="PaperFlow logo" width={28} height={28} priority className="h-7 w-7 object-contain" />
            </span>
            <span className="hidden sm:block">
              <span className="block font-semibold tracking-[-0.02em] text-[#1f2d32]">PaperFlow</span>
              <span className="block text-[10px] uppercase tracking-[0.13em] text-[#87918f]">Academic library</span>
            </span>
          </Link>

          <form onSubmit={submitSearch} className="mx-auto hidden w-full max-w-[660px] md:block">
            <label className="flex h-10 items-center gap-2 rounded-lg border border-[#dfe4e1] bg-[#f8faf8] px-3 text-[#7d888c] transition-colors focus-within:border-[#6d9c68] focus-within:bg-white">
              <Search className="h-[17px] w-[17px] shrink-0" />
              <input
                ref={searchInputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="min-w-0 flex-1 bg-transparent text-[13px] text-[#1f2d32] outline-none placeholder:text-[#8c979a]"
                placeholder="Search courses, documents, universities, or exam papers"
                aria-label="Search PaperFlow"
              />
              <kbd className="hidden shrink-0 rounded border border-[#dfe4e1] bg-white px-1.5 py-0.5 text-[10px] font-semibold text-[#8b9597] md:inline-flex" title="Focus search (Command K or Control K)">⌘ K</kbd>
            </label>
          </form>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Link href="/upload" className="hidden items-center gap-2 rounded-lg border border-[#d9e0da] px-3 py-2 text-[13px] font-medium text-[#43534c] transition-colors hover:border-[#a8c2a1] hover:bg-[#f3f8f1] sm:flex">
              <UploadCloud className="h-4 w-4" />
              <span>Upload</span>
            </Link>
            <button type="button" aria-label="Account menu" className="flex h-9 w-9 items-center justify-center rounded-full bg-[#ece5db] text-[12px] font-semibold text-[#6b5543] ring-2 ring-white">
              PF
            </button>
          </div>
        </div>
      </header>

      <aside className={`fixed bottom-0 left-0 top-16 z-30 w-[248px] border-r border-[#e5e8e4] bg-white px-4 py-5 transition-transform md:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-5 px-1">
          <Link href="/upload" onClick={() => setMobileOpen(false)} className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-[#3e8d3c] text-[13px] font-semibold text-white shadow-[0_2px_5px_rgba(62,141,60,0.14)] transition-colors hover:bg-[#337733]">
            <UploadCloud className="h-4 w-4" />
            Upload a document
          </Link>
        </div>

        <nav className="space-y-6" aria-label="Primary navigation">
          <div>
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#a0a9a8]">Main</p>
            <div className="space-y-0.5">{renderItems(primaryItems)}</div>
          </div>

          <div>
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#a0a9a8]">Your library</p>
            <div className="space-y-0.5">{renderItems(savedItems)}</div>
          </div>

          <div>
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#a0a9a8]">Explore</p>
            <div className="space-y-0.5">{renderItems(exploreItems)}</div>
          </div>
        </nav>

      </aside>
    </>
  );
};
