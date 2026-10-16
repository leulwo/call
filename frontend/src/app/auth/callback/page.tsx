"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const finish = async () => {
      const supabase = getSupabaseBrowserClient();
      // PKCE flow: exchange ?code=... for a session
      const code = new URLSearchParams(window.location.search).get("code");
      if (code) {
        await supabase.auth.exchangeCodeForSession(code);
      }
      const rawNext = new URLSearchParams(window.location.search).get("next") || "/";
      const isSafeRedirect =
        rawNext.startsWith("/") && !rawNext.startsWith("//") && !rawNext.startsWith("/\\");
      router.replace(isSafeRedirect ? rawNext : "/");
    };
    finish();
  }, [router]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center text-sm text-stone-500">
      Signing you in...
    </div>
  );
}
