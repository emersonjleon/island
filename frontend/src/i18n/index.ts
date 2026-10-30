import i18next, { type i18n } from "i18next";

import enCommon from "../locales/en/common.json";
import esCommon from "../locales/es/common.json";

export const SUPPORTED_LANGUAGES = ["en", "es"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

/** The page language, as Django set it on <html lang>. */
export function pageLanguage(doc: Document = document): Language {
  const lang = (doc.documentElement.lang || "en").split("-")[0];
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(lang ?? "") ? (lang as Language) : "en";
}

/** Initialise i18next. Frontend packages add their own namespaces with addResourceBundle. */
export async function initI18n(lng: Language): Promise<i18n> {
  await i18next.init({
    lng,
    fallbackLng: "en",
    defaultNS: "common",
    ns: ["common"],
    resources: { en: { common: enCommon }, es: { common: esCommon } },
    interpolation: { escapeValue: false },
  });
  return i18next;
}
