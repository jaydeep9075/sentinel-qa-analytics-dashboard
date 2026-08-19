"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { IngestionProvider } from "@/lib/IngestionContext";
import { RBProvider } from "@/lib/RBContext";
import { SuggestionsProvider } from "@/lib/SuggestionsContext";
import BrandLogo from "@/components/BrandLogo";

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
  // Start at null (matches what the server renders, since it has no
  // localStorage) so hydration doesn't mismatch — the real token is read
  // client-side only, after mount. This lets Next.js server-render the
  // skeleton below instead of shipping a blank page for this whole route
  // (previously wrapped in next/dynamic(..., { ssr: false })).
  const [token, setToken] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("token");
    setToken(stored);
    setChecked(true);
    if (!stored) {
      router.replace("/login");
    }
  }, [router]);

  if (!checked || !token) {
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
