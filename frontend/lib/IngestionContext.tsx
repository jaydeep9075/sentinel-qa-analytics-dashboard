"use client";
import React, { createContext, useContext, useState, useEffect } from "react";
import { listIngestions } from "./api";

interface Ingestion {
  id: string;
  summary: string;
}

interface IngestionContextType {
  ingestions: Ingestion[];
  selectedIngestion: string | null;
  setSelectedIngestion: (id: string) => void;
  loading: boolean;
}

const IngestionContext = createContext<IngestionContextType>({
  ingestions: [],
  selectedIngestion: null,
  setSelectedIngestion: () => {},
  loading: false,
});

export const useIngestion = () => useContext(IngestionContext);

export const IngestionProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [ingestions, setIngestions] = useState<Ingestion[]>([]);
  const [selectedIngestion, setSelectedIngestion] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listIngestions()
      .then((data) => {
        setIngestions(data.ingestions);
        if (data.ingestions.length > 0) {
          const saved = localStorage.getItem("selectedIngestion");
          if (saved && data.ingestions.some((i: Ingestion) => i.id === saved)) {
            setSelectedIngestion(saved);
          } else {
            setSelectedIngestion(data.ingestions[0].id);
          }
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSetSelectedIngestion = (id: string) => {
    setSelectedIngestion(id);
    localStorage.setItem("selectedIngestion", id);
  };

  return (
    <IngestionContext.Provider
      value={{ ingestions, selectedIngestion, setSelectedIngestion: handleSetSelectedIngestion, loading }}
    >
      {children}
    </IngestionContext.Provider>
  );
};
