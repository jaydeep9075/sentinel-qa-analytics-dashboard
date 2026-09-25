"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { IngestionProvider } from "@/lib/IngestionContext";
import { RBProvider } from "@/lib/RBContext";
import { SuggestionsProvider } from "@/lib/SuggestionsContext";
import BrandLogo from "@/components/BrandLogo";

function subscribeToToken(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

// `undefined` on the server and during hydration, then the real value. This is
// what lets Next.js server-render the skeleton below instead of shipping a
// blank page for the whole route (it was previously wrapped in
// next/dynamic(..., { ssr: false })) without a hydration mismatch.
function useStoredToken(): string | null | undefined {
  return useSyncExternalStore(
    subscribeToToken,
    () => localStorage.getItem("token"),
    () => undefined
  );
}

function AuthGateSkeleton() {
  return (
    <div className="min-h-screen bg-[var(--background)] flex flex-col items-center justify-center gap-4">
      <BrandLogo size={52} />
      <div className="w-10 h-10 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin shadow-[0_0_15px_rgba(0,240,255,0.2)]" />
      <span className="text-[10px] text-slate-500 dark:text-white/20 uppercase tracking-widest font-semibold">Authenticating</span>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const token = useStoredToken();

  useEffect(() => {
    // The "you have no project" bounce lives in the page, not here: RBProvider
    // already fetches /projects for the selector, and a second /auth/me round
    // trip on every dashboard mount bought nothing the page did not already
    // know a moment later.
    if (token === null) {
      router.replace("/login");
    }
  }, [token, router]);

  if (!token) {
    return <AuthGateSkeleton />;
  }

  return (
    <RBProvider>
      <IngestionProvider>
        <SuggestionsProvider>{children}</SuggestionsProvider>
      </IngestionProvider>
    </RBProvider>
  );
}
