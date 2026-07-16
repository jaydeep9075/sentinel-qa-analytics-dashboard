"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useRB } from "./RBContext";
import { useIngestion } from "./IngestionContext";
import { getRoleSuggestions, getAdaptiveRoleSuggestions, type Suggestions } from "./roleSuggestions";

interface SuggestionsContextType {
  suggestions: Suggestions;
}

const SuggestionsContext = createContext<SuggestionsContextType | undefined>(undefined);

/**
 * Fetches /suggestions exactly once per (ingestion, role, project) combination
 * and shares the result with any consumer (FloatingChat, FloatingChart), instead
 * of each component independently firing its own request on mount — the two
 * near-duplicate requests were doubling the LLM-backed /suggestions round trip
 * right at dashboard load.
 */
export function SuggestionsProvider({ children }: { children: React.ReactNode }) {
  const { selectedRole, selectedProject } = useRB();
  const { selectedIngestion } = useIngestion();
  const [suggestions, setSuggestions] = useState<Suggestions>(getRoleSuggestions(selectedRole || ""));

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const fallback = getRoleSuggestions(selectedRole || "");
      if (!cancelled) setSuggestions(fallback);
      if (!selectedIngestion) return;
      const dynamic = await getAdaptiveRoleSuggestions(selectedIngestion, selectedRole, selectedProject);
      if (!cancelled) setSuggestions(dynamic);
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [selectedRole, selectedProject, selectedIngestion]);

  return (
    <SuggestionsContext.Provider value={{ suggestions }}>{children}</SuggestionsContext.Provider>
  );
}

export function useSuggestions() {
  const ctx = useContext(SuggestionsContext);
  if (!ctx) throw new Error("useSuggestions must be used within SuggestionsProvider");
  return ctx;
}
