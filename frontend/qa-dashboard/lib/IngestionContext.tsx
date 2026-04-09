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
          setSelectedIngestion(data.ingestions[0].id);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <IngestionContext.Provider
      value={{ ingestions, selectedIngestion, setSelectedIngestion, loading }}
    >
      {children}
    </IngestionContext.Provider>
  );
};
