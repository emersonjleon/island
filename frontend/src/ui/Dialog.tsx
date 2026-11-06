// Modal dialog shell and an Escape hook shared by the HUD dialogs.
import type { TFunction } from "i18next";
import type { ComponentChildren } from "preact";
import { useEffect } from "preact/hooks";

export function Dialog(props: { title: string; t: TFunction; closeKey: string; onClose(): void; children: ComponentChildren }) {
  return (
    <div class="hud-overlay" onPointerDown={(e) => { if (e.target === e.currentTarget) props.onClose(); }}>
      <div class="hud-dialog" role="dialog" aria-modal="true" aria-label={props.title}>
        <header>
          <h2>{props.title}</h2>
          <button type="button" class="quiet" onClick={props.onClose}>{props.t(props.closeKey)}</button>
        </header>
        {props.children}
      </div>
    </div>
  );
}

export function useEscape(fn: () => void): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); fn(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [fn]);
}
