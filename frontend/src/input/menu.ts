// Small right-click menu (DOM over the canvas).
import type { TFunction } from "i18next";

import type { MenuItem } from "./controller";

export function menuFactory(host: HTMLElement, t: TFunction) {
  return (x: number, y: number, items: MenuItem[]): (() => void) => {
    const menu = document.createElement("div");
    menu.className = "game-menu";
    menu.setAttribute("role", "menu");
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    const close = () => {
      menu.remove();
      window.removeEventListener("keydown", onKey, true);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); close(); }
    };
    for (const it of items) {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "menuitem");
      b.textContent = t(`input:menu.${it.label}`);
      b.addEventListener("pointerdown", (e) => e.stopPropagation());
      b.addEventListener("click", () => { close(); it.run(); });
      menu.appendChild(b);
    }
    host.appendChild(menu);
    window.addEventListener("keydown", onKey, true);
    (menu.firstElementChild as HTMLButtonElement | null)?.focus();
    return close;
  };
}
