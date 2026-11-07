import type { i18n } from "i18next";

import enErrors from "../locales/en/errors.json";
import enEvents from "../locales/en/events.json";
import enHud from "../locales/en/hud.json";
import esErrors from "../locales/es/errors.json";
import esEvents from "../locales/es/events.json";
import esHud from "../locales/es/hud.json";

export function addHudCatalogues(i: i18n): void {
  i.addResourceBundle("en", "hud", enHud);
  i.addResourceBundle("en", "errors", enErrors);
  i.addResourceBundle("en", "events", enEvents);
  i.addResourceBundle("es", "hud", esHud);
  i.addResourceBundle("es", "errors", esErrors);
  i.addResourceBundle("es", "events", esEvents);
}
