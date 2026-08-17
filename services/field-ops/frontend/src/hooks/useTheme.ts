/**
 * useTheme — light/dark theme with an explicit user override.
 *
 * Three states, deliberately:
 *
 *   "system"  follow the OS setting, and keep following it as it changes
 *   "light"   force light, ignore the OS
 *   "dark"    force dark, ignore the OS
 *
 * "system" is not a nicety here. Android and iOS both switch to dark on a
 * schedule or on ambient light, which is exactly the behaviour someone wants
 * when they start a session at 05:00 and finish under midday sun. But an
 * operator who has decided the screen is unreadable in the field needs to
 * pin it and have that stick — hence the override, persisted.
 *
 * The resolved theme is written to <html data-theme>, which is the attribute
 * Pico.css keys on, and mirrored into <meta name="theme-color"> so the PWA's
 * browser chrome matches rather than flashing white.
 */

import { useCallback, useEffect, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "field_ops_theme";

/** Pico's brand blue (light) and a dark-mode equivalent, for browser chrome. */
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: "#1a56a4",
  dark: "#11191f",
};

function readStoredChoice(): ThemeChoice {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    // Private mode / storage disabled — fall through to system.
  }
  return "system";
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function resolve(choice: ThemeChoice): ResolvedTheme {
  if (choice === "system") return systemPrefersDark() ? "dark" : "light";
  return choice;
}

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(readStoredChoice);
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolve(readStoredChoice()));

  // Apply to the DOM whenever the choice changes, and — when following the
  // system — whenever the OS flips underneath us.
  useEffect(() => {
    const apply = () => {
      const next = resolve(choice);
      setResolved(next);
      document.documentElement.setAttribute("data-theme", next);
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", THEME_COLOR[next]);
    };

    apply();

    if (choice !== "system") return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [choice]);

  const setTheme = useCallback((next: ThemeChoice) => {
    setChoice(next);
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Non-fatal: the theme still applies for this session.
    }
  }, []);

  /** system → light → dark → system. */
  const cycleTheme = useCallback(() => {
    setTheme(choice === "system" ? "light" : choice === "light" ? "dark" : "system");
  }, [choice, setTheme]);

  return { choice, resolved, setTheme, cycleTheme };
}
