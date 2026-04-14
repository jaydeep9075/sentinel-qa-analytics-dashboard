"use client";
import React, { createContext, useContext, useState, useEffect } from "react";
import { listIngestions } from "./api";

export interface Ingestion {
  id: string;          // real folder name — used in API headers, never shown
  build_label: string; // e.g. "Build 1", "Build 2"
  summary: string;
  created: number;
}

interface IngestionContextType {
  ingestions: Ingestion[];
  selectedIngestion: string | null;   // stores the real folder id
  selectedBuildLabel: string | null;  // the friendly label for the selected ingestion
  setSelectedIngestion: (id: string) => void;
  loading: boolean;
}

const IngestionContext = createContext<IngestionContextType>({
  ingestions: [],
  selectedIngestion: null,
  selectedBuildLabel: null,
  setSelectedIngestion: () => {},
  loading: false,
});

export const useIngestion = () => useContext(IngestionContext);

export const IngestionProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [ingestions, setIngestions] = useState<Ingestion[]>([]);
  const [selectedIngestion, setSelectedIngestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listIngestions()
      .then((data) => {
        const list: Ingestion[] = data.ingestions;
        setIngestions(list);
        if (list.length > 0) {
          // Try to restore last selected by real folder id
          const saved = localStorage.getItem("selectedIngestion");
          const stillExists = saved && list.some((i) => i.id === saved);
          // If the saved ingestion was deleted, fall back to the newest (index 0)
          setSelectedIngestion(stillExists ? saved! : list[0].id);
        }
      })
      .finally(() => setLoading(false));
  }, []);

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
        loading,
      }}
    >
      {children}
    </IngestionContext.Provider>
  );
};
