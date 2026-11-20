import type { i18n } from "i18next";

import en from "../locales/en/input.json";
import es from "../locales/es/input.json";
import zh from "../locales/zh/input.json";

export function addInputCatalogue(i: i18n): void {
  i.addResourceBundle("en", "input", en);
  i.addResourceBundle("es", "input", es);
  i.addResourceBundle("zh", "input", zh);
}
