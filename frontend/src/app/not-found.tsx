import React from "react";
import Link from "next/link";
import Image from "next/image";
import { BookOpen } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center space-y-6 max-w-md mx-auto">
      <div className="relative h-44 w-44">
        <Image
          src="/Page-Not-Found-1--Streamline-Brooklyn.svg"
          alt="Page not found"
          fill
          className="object-contain"
        />
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-stone-900">Document Not Found</h1>
        <p className="text-xs text-stone-500">
          The exam paper or page you are looking for might have been moved or does not exist in the library catalog.
        </p>
      </div>

      <Link href="/">
        <Button variant="primary" size="md" icon={<BookOpen className="h-4 w-4" />}>
          Back to Library Catalog
        </Button>
      </Link>
    </div>
  );
}
