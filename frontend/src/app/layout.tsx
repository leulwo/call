import type { Metadata } from "next";
import { Navbar } from "@/components/layout/Navbar";
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
        <Navbar />
        <main className="min-h-screen bg-[#fbfaf7] pt-16 md:ml-[248px]">
          <div className="mx-auto w-full max-w-[1500px] px-4 py-6 sm:px-7 sm:py-8">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
