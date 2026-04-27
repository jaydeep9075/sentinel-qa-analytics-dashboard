"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { IngestionProvider } from "@/lib/IngestionContext";
import { RBProvider } from "@/lib/RBContext";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [isAuth, setIsAuth] = useState<boolean | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      router.replace("/login");
    } else {
      setIsAuth(true);
    }
  }, [router]);

  if (isAuth === null) {
    return (
      <div className="min-h-screen bg-[var(--background)] flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin shadow-[0_0_15px_rgba(0,240,255,0.2)]" />
        <span className="text-[10px] text-slate-500 dark:text-white/20 uppercase tracking-widest font-semibold">Authenticating</span>
      </div>
    );
  }

  return (
    <RBProvider>
      <IngestionProvider>{children}</IngestionProvider>
    </RBProvider>
  );
}
