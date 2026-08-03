// Lightweight i18n for the MASIL dashboard.
//
// Design: Korean is the source language and the dictionary KEY. `t("한국어")`
// returns the current locale's translation, falling back to the Korean source
// when the locale is Korean or a key is missing. The active locale is a module
// variable (source of truth for `t`); the React tree re-reads it whenever App
// re-renders after `setLocale`, so no per-component context threading is needed.

import en from "./locales/en";

// ko/en only for the finals — zh/ja/vi packs were removed (unreviewed
// translations); re-add from git history after the competition if needed.
export type Locale = "ko" | "en";

export const LOCALE_ORDER: Locale[] = ["en", "ko"];

export const LOCALE_META: Record<Locale, { label: string; short: string; htmlLang: string }> = {
  ko: { label: "한국어", short: "KO", htmlLang: "ko" },
  en: { label: "English", short: "EN", htmlLang: "en" }
};

const DICTIONARIES: Record<Exclude<Locale, "ko">, Record<string, string>> = {
  en
};

const LOCALE_STORAGE_KEY = "masil.locale";

function initialLocale(): Locale {
  // ALWAYS English on entry (팀 결정 8/3) — a previous visitor's saved choice
  // must not leak into a judge's first screen. Switching applies per session.
  return "en";
}

let currentLocale: Locale = initialLocale();
if (typeof document !== "undefined") {
  document.documentElement.lang = LOCALE_META[currentLocale].htmlLang;
}

export function getLocale(): Locale {
  return currentLocale;
}

export function setLocale(locale: Locale): void {
  currentLocale = locale;
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // storage unavailable — the in-memory locale still applies for this session
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = LOCALE_META[locale].htmlLang;
  }
}

/** Translate a Korean source string into the active locale. */
export function t(korean: string): string {
  if (currentLocale === "ko") return korean;
  return DICTIONARIES[currentLocale]?.[korean] ?? korean;
}

/**
 * Interpolating variant: `tf("{n}개 사례", { n: 180 })`.
 * The Korean key keeps the `{name}` placeholders; translations mirror them.
 */
export function tf(korean: string, vars: Record<string, string | number>): string {
  let out = t(korean);
  for (const [key, value] of Object.entries(vars)) {
    out = out.replaceAll(`{${key}}`, String(value));
  }
  return out;
}
