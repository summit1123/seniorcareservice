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

let currentLocale: Locale = "ko";

export function getLocale(): Locale {
  return currentLocale;
}

export function setLocale(locale: Locale): void {
  currentLocale = locale;
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
