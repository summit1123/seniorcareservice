// Lightweight i18n for the MASIL dashboard.
//
// Design: Korean is the source language and the dictionary KEY. `t("한국어")`
// returns the current locale's translation, falling back to the Korean source
// when the locale is Korean or a key is missing. The active locale is a module
// variable (source of truth for `t`); the React tree re-reads it whenever App
// re-renders after `setLocale`, so no per-component context threading is needed.

import en from "./locales/en";
import ja from "./locales/ja";
import vi from "./locales/vi";
import zh from "./locales/zh";

export type Locale = "ko" | "en" | "zh" | "ja" | "vi";

export const LOCALE_ORDER: Locale[] = ["ko", "en", "zh", "ja", "vi"];

export const LOCALE_META: Record<Locale, { label: string; short: string; htmlLang: string }> = {
  ko: { label: "한국어", short: "KO", htmlLang: "ko" },
  en: { label: "English", short: "EN", htmlLang: "en" },
  zh: { label: "简体中文", short: "中", htmlLang: "zh-Hans" },
  ja: { label: "日本語", short: "日", htmlLang: "ja" },
  vi: { label: "Tiếng Việt", short: "VI", htmlLang: "vi" }
};

const DICTIONARIES: Record<Exclude<Locale, "ko">, Record<string, string>> = {
  en,
  zh,
  ja,
  vi
};

const LOCALE_STORAGE_KEY = "masil.locale";

function initialLocale(): Locale {
  // Persisted choice wins; otherwise ENGLISH — GAIP is a Singapore competition,
  // so the very first screen must open in English.
  try {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(LOCALE_STORAGE_KEY) : null;
    if (saved && (LOCALE_ORDER as string[]).includes(saved)) return saved as Locale;
  } catch {
    // storage unavailable (private mode 등) — fall through
  }
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
