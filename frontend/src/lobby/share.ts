// Settings codes: "copy" buttons on the game page, and the create form's code field.

/** Copy ``text`` to the clipboard; falls back to selecting a hidden textarea. */
export async function copyText(text: string, doc: Document = document): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the old way
  }
  const area = doc.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  doc.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = doc.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  return ok;
}

/** How long a "Copied" label stays on a copy button. */
const COPIED_MS = 1800;

/** Buttons with ``data-copy`` copy that text and say ``data-copied`` for a moment. */
export function initCopyButtons(root: ParentNode): void {
  for (const button of root.querySelectorAll<HTMLButtonElement>("button[data-copy]")) {
    const label = button.textContent ?? "";
    button.addEventListener("click", async () => {
      const ok = await copyText(button.dataset.copy ?? "");
      if (!ok) {
        root.querySelector<HTMLInputElement>("[data-share-value]")?.select();
        return;
      }
      button.textContent = button.dataset.copied ?? label;
      window.setTimeout(() => { button.textContent = label; }, COPIED_MS);
    });
  }
  for (const input of root.querySelectorAll<HTMLInputElement>("[data-share-value]")) {
    input.addEventListener("focus", () => input.select());
  }
}

/** True when the code field holds something (spaces and line breaks do not count). */
export function hasCode(value: string): boolean {
  return value.replace(/\s+/g, "") !== "";
}
