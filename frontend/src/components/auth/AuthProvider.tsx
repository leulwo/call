"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { setAccessTokenProvider } from "@/lib/api";

interface AuthState {
  session: Session | null;
  user: User | null;
  displayName: string;
  /** Google profile photo URL, when available. */
  avatarUrl: string | null;
  loading: boolean;
  /** True when env vars are missing — the UI shows auth as unavailable instead of a sign-in button that would throw. */
  configured: boolean;
  signInWithGoogle: (redirectTo?: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Current access token for calling the backend, or null when signed out. */
  getAccessToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthState | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const configured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY &&
    !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.startsWith("PASTE_YOUR")
  );

  useEffect(() => {
    setAccessTokenProvider(async () => {
      if (!configured) return null;
      const supabase = getSupabaseBrowserClient();
      const { data } = await supabase.auth.getSession();
      const session = data.session;
      if (!session?.access_token) return null;
      // Refresh ahead of expiry instead of handing the backend a dead token
      // (access tokens last ~1 hour; getSession may return a stale cache).
      const expiresAt = session.expires_at ?? 0;
      if (expiresAt - Math.floor(Date.now() / 1000) < 60) {
        const { data: refreshed } = await supabase.auth.refreshSession();
        return refreshed.session?.access_token ?? session.access_token;
      }
      return session.access_token;
    });
  }, [configured]);

  useEffect(() => {
    if (!configured) {
      setLoading(false);
      return;
    }
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });
    return () => subscription.subscription.unsubscribe();
  }, [configured]);

  const signInWithGoogle = useCallback(async (redirectTo?: string) => {
    const supabase = getSupabaseBrowserClient();
    const origin = window.location.origin;
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${origin}/auth/callback?next=${encodeURIComponent(redirectTo || "/")}`,
      },
    });
  }, []);

  const signOut = useCallback(async () => {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
    setSession(null);
  }, []);

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    if (!session) return null;
    const supabase = getSupabaseBrowserClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }, [session]);

  const value = useMemo<AuthState>(() => ({
    session,
    user: session?.user ?? null,
    displayName:
      (session?.user?.user_metadata?.full_name as string) ||
      (session?.user?.user_metadata?.name as string) ||
      (session?.user?.email as string)?.split("@")[0] ||
      "",
    avatarUrl: (session?.user?.user_metadata?.avatar_url as string) || (session?.user?.user_metadata?.picture as string) || null,
    loading,
    configured,
    signInWithGoogle,
    signOut,
    getAccessToken,
  }), [session, loading, configured, signInWithGoogle, signOut, getAccessToken]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
