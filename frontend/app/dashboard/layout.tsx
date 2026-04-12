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
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <RBProvider>
      <IngestionProvider>{children}</IngestionProvider>
    </RBProvider>
  );
}
