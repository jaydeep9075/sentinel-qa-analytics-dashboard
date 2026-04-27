"use client";

import { useEffect } from "react";
import { applyTheme, getStoredTheme } from "@/lib/theme";

export default function ThemeInitializer() {
  useEffect(() => {
    applyTheme(getStoredTheme());
  }, []);

  return null;
}
