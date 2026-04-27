"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

export type ThemeMode = "dark" | "light";

const THEME_KEY = "theme";
let currentTheme: ThemeMode = "dark";
let isInitialized = false;
const listeners = new Set<() => void>();

export function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "dark";
  }
  const savedTheme = localStorage.getItem(THEME_KEY);
  return savedTheme === "light" ? "light" : "dark";
}

export function applyTheme(theme: ThemeMode) {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.setAttribute("data-theme", theme);
}

function initializeThemeStore() {
  if (isInitialized || typeof window === "undefined") return;
  currentTheme = getStoredTheme();
  applyTheme(currentTheme);
  isInitialized = true;
}

function notifyListeners() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return currentTheme;
}

function setThemeInternal(nextTheme: ThemeMode) {
  currentTheme = nextTheme;
  if (typeof window !== "undefined") {
    localStorage.setItem(THEME_KEY, nextTheme);
  }
  applyTheme(nextTheme);
  notifyListeners();
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, () => "dark");

  useEffect(() => {
    initializeThemeStore();
    notifyListeners();
  }, []);

  const setTheme = useCallback((nextTheme: ThemeMode) => {
    setThemeInternal(nextTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeInternal(currentTheme === "dark" ? "light" : "dark");
  }, []);

  return { theme, setTheme, toggleTheme, isDark: theme === "dark" };
}
