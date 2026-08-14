"use client";
import React, { createContext, useCallback, useContext, useState, useEffect } from "react";
import { listIngestions, readCachedIngestions } from "./api";

export interface Ingestion {
  id: string;          // real folder name — used in API headers, never shown
  build_label: string; // e.g. "Build 1", "Build 2"
  display_name?: string; // optional user-supplied name, preferred over build_label when set
  summary: string;
  created: number;
}

interface IngestionContextType {
  ingestions: Ingestion[];
  selectedIngestion: string | null;   // stores the real folder id
  selectedBuildLabel: string | null;  // the friendly label for the selected ingestion
  setSelectedIngestion: (id: string) => void;
  refreshIngestions: () => Promise<void>;
  loading: boolean;
}

const IngestionContext = createContext<IngestionContextType>({
  ingestions: [],
  selectedIngestion: null,
  selectedBuildLabel: null,
  setSelectedIngestion: () => {},
  refreshIngestions: async () => {},
  loading: false,
});

export const useIngestion = () => useContext(IngestionContext);

export const IngestionProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [ingestions, setIngestions] = useState<Ingestion[]>(() => {
    const cached = readCachedIngestions();
    return ((cached?.ingestions || []) as Ingestion[]) || [];
  });
  const [selectedIngestion, setSelectedIngestion] = useState<string | null>(() => {
    const cached = readCachedIngestions();
    const list = ((cached?.ingestions || []) as Ingestion[]) || [];
    if (!list.length || typeof window === "undefined") return null;
    const saved = localStorage.getItem("selectedIngestion");
    const stillExists = saved && list.some((i) => i.id === saved);
    return stillExists ? saved! : list[0].id;
  });
  const [loading, setLoading] = useState(() => {
    const cached = readCachedIngestions();
    const list = ((cached?.ingestions || []) as Ingestion[]) || [];
    return list.length === 0;
  });

  const applyIngestionList = useCallback((list: Ingestion[]) => {
    setIngestions(list);
    if (list.length === 0) {
      setSelectedIngestion(null);
      return;
    }
    const saved = localStorage.getItem("selectedIngestion");
    const stillExists = saved && list.some((i) => i.id === saved);
    setSelectedIngestion(stillExists ? saved! : list[0].id);
  }, []);

  const refreshIngestions = useCallback(async () => {
    const data = await listIngestions(true);
    const list = (data?.ingestions || []) as Ingestion[];
    applyIngestionList(list);
  }, [applyIngestionList]);

  useEffect(() => {
    const hasCached = ingestions.length > 0;

    let cancelled = false;
    listIngestions(hasCached)
      .then((data) => {
        if (cancelled) return;
        const list = (data?.ingestions || []) as Ingestion[];
        applyIngestionList(list);
      })
      .catch(() => {
        if (!hasCached && !cancelled) {
          setIngestions([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        refreshIngestions().catch(() => {
          // Keep existing list on transient refresh failures.
        });
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [applyIngestionList, refreshIngestions, ingestions.length]);

  const handleSetSelectedIngestion = (id: string) => {
    setSelectedIngestion(id);
    localStorage.setItem("selectedIngestion", id);
  };

  const selectedBuildLabel =
    ingestions.find((i) => i.id === selectedIngestion)?.build_label ?? null;

  return (
    <IngestionContext.Provider
      value={{
        ingestions,
        selectedIngestion,
        selectedBuildLabel,
        setSelectedIngestion: handleSetSelectedIngestion,
        refreshIngestions,
        loading,
      }}
    >
      {children}
    </IngestionContext.Provider>
  );
};
