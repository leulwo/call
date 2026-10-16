import type { Metadata } from "next";
import { Suspense } from "react";
import Image from "next/image";
import { Navbar } from "@/components/layout/Navbar";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { NoConnectionOverlay } from "@/components/system/NoConnectionOverlay";
import "./globals.css";

export const metadata: Metadata = {
  title: "PaperFlow — Academic document library",
  description: "Find, read, save, and share clean academic documents, lecture notes, and exam papers.",
  icons: {
    icon: "/Logo.png",
    shortcut: "/Logo.png",
    apple: "/Logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#fbfaf7] text-[#1f2d32] antialiased">
        <AuthProvider>
          <NoConnectionOverlay />
          <Suspense fallback={
            <header className="fixed inset-x-0 top-0 z-40 h-16 border-b border-[#e5e8e4] bg-[#fffefa]">
              <div className="flex h-full items-center gap-2.5 px-4 md:px-7">
                <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-[#365f39]">
                  <Image src="/Logo.png" alt="" width={28} height={28} priority />
                </span>
                <span className="text-[14px] font-semibold text-[#1f2d32]">PaperFlow</span>
                <span className="mx-auto hidden h-10 w-full max-w-[660px] rounded-lg border border-[#dfe4e1] bg-[#f8faf8] md:block" aria-hidden="true" />
              </div>
            </header>
          }>
            <Navbar />
          </Suspense>
          <main className="paperflow-main min-h-screen pt-16 md:ml-[248px]">
            <div className="mx-auto w-full max-w-[1500px] px-4 py-6 sm:px-7 sm:py-8">
              {children}
            </div>
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
