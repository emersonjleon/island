import type { i18n } from "i18next";

import en from "../locales/en/chat.json";
import es from "../locales/es/chat.json";

export function addChatCatalogue(i: i18n): void {
  i.addResourceBundle("en", "chat", en);
  i.addResourceBundle("es", "chat", es);
}

/** Text for a chat refusal code from the server ("chat.too_long" -> chat:errors.too_long). */
export function chatErrorKey(code: string): string {
  return `chat:errors.${code.replace(/^chat\./, "")}`;
}
