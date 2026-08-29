"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

export type ThemeMode = "dark" | "light";

const THEME_KEY = "theme";
// Light is the default for anyone who hasn't chosen yet — a first-time
// visitor (or someone who just signed out) should land in light mode, not
// carry over dark from a previous build's default.
let currentTheme: ThemeMode = "light";
let isInitialized = false;
const listeners = new Set<() => void>();

export function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") {
    return "light";
  }
  const savedTheme = localStorage.getItem(THEME_KEY);
  return savedTheme === "dark" ? "dark" : "light";
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
  const theme = useSyncExternalStore(subscribe, getSnapshot, () => "light");

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
