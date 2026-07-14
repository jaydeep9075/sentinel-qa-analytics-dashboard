"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { IngestionProvider } from "@/lib/IngestionContext";
import { RBProvider } from "@/lib/RBContext";

function DashboardLayoutInner({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<Record<string, string | string[] | undefined>>;
}) {
  void params;
  const router = useRouter();
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

  useEffect(() => {
    if (!token) {
      router.replace("/login");
    }
  }, [router, token]);

  if (!token) {
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

const DashboardLayout = dynamic(async () => DashboardLayoutInner, {
  ssr: false,
});

export default DashboardLayout;
