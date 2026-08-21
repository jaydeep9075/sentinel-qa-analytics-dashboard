/* eslint-disable react-hooks/set-state-in-effect */
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RBProvider } from "@/lib/RBContext";
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

export default function ProjectsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
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

  return <RBProvider>{children}</RBProvider>;
}
