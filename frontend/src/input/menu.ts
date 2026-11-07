// Small right-click / tap menu (DOM over the canvas).
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
    // Keep the menu on screen (a tap near the bottom or right edge of a phone).
    const margin = 8;
    const left = Math.min(x, host.clientWidth - menu.offsetWidth - margin);
    const top = Math.min(y, host.clientHeight - menu.offsetHeight - margin);
    menu.style.left = `${Math.max(margin, left)}px`;
    menu.style.top = `${Math.max(margin, top)}px`;
    window.addEventListener("keydown", onKey, true);
    (menu.firstElementChild as HTMLButtonElement | null)?.focus();
    return close;
  };
}
