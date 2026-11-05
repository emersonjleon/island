// Actions and rebindable key bindings. A combo is "Mod+Mod+Code" using
// KeyboardEvent.code (layout independent), e.g. "Shift+KeyW", "ArrowUp", "Digit1".

export const ACTIONS = [
  "move_up", "move_down", "move_left", "move_right",
  "select_next", "select_1", "select_2", "select_3",
  "build_road", "build_settlement", "build_city", "confirm", "cancel",
  "camera_up", "camera_down", "camera_left", "camera_right",
  "zoom_in", "zoom_out", "center_selected",
  "buy_dev_card", "open_trade",
] as const;
export type Action = (typeof ACTIONS)[number];
export type Bindings = Record<Action, string[]>;

/** Defaults from the Controls table in docs/GAME_DESIGN.md. */
export const DEFAULT_BINDINGS: Bindings = {
  move_up: ["KeyW", "ArrowUp"],
  move_down: ["KeyS", "ArrowDown"],
  move_left: ["KeyA", "ArrowLeft"],
  move_right: ["KeyD", "ArrowRight"],
  select_next: ["Tab"],
  select_1: ["Digit1"],
  select_2: ["Digit2"],
  select_3: ["Digit3"],
  build_road: ["KeyR"],
  build_settlement: ["KeyE"],
  build_city: ["KeyC"],
  confirm: ["Enter", "NumpadEnter"],
  cancel: ["Escape"],
  camera_up: ["Shift+KeyW", "Shift+ArrowUp"],
  camera_down: ["Shift+KeyS", "Shift+ArrowDown"],
  camera_left: ["Shift+KeyA", "Shift+ArrowLeft"],
  camera_right: ["Shift+KeyD", "Shift+ArrowRight"],
  zoom_in: ["Equal", "Shift+Equal", "NumpadAdd"],
  zoom_out: ["Minus", "NumpadSubtract"],
  center_selected: ["Space"],
  buy_dev_card: ["KeyV"],
  open_trade: ["KeyT"],
};

const MODIFIERS = ["Ctrl", "Alt", "Shift", "Meta"] as const;

/** The combo string for a key event (modifiers in a fixed order). */
export function comboOf(e: Pick<KeyboardEvent, "code" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">): string {
  const mods = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && "Shift", e.metaKey && "Meta"].filter(Boolean);
  return [...mods, e.code].join("+");
}

/** Put a combo's modifiers in the fixed order so user-typed combos compare equal. */
export function normaliseCombo(combo: string): string {
  const parts = combo.split("+");
  const code = parts.pop() ?? "";
  const mods = MODIFIERS.filter((m) => parts.includes(m));
  return [...mods, code].join("+");
}

/** Defaults overlaid with the user's saved map; unknown actions and bad values are dropped. */
export function mergeBindings(saved: unknown): Bindings {
  const out: Bindings = { ...DEFAULT_BINDINGS };
  if (!saved || typeof saved !== "object") return out;
  for (const [action, combos] of Object.entries(saved as Record<string, unknown>)) {
    if (!(ACTIONS as readonly string[]).includes(action) || !Array.isArray(combos)) continue;
    out[action as Action] = combos.filter((c): c is string => typeof c === "string").map(normaliseCombo);
  }
  return out;
}

/** Only the actions whose combos differ from the defaults (what we store). */
export function diffFromDefaults(b: Bindings): Partial<Bindings> {
  const out: Partial<Bindings> = {};
  for (const a of ACTIONS) if (b[a].join(",") !== DEFAULT_BINDINGS[a].join(",")) out[a] = b[a];
  return out;
}

/** Combos bound to more than one action: combo -> actions. */
export function conflicts(b: Bindings): Map<string, Action[]> {
  const seen = new Map<string, Action[]>();
  for (const a of ACTIONS) for (const c of b[a]) seen.set(c, [...(seen.get(c) ?? []), a]);
  return new Map([...seen].filter(([, as]) => as.length > 1));
}

/** combo -> action lookup (first action wins on a conflict). */
export function keymap(b: Bindings): Map<string, Action> {
  const m = new Map<string, Action>();
  for (const a of ACTIONS) for (const c of b[a]) if (!m.has(c)) m.set(c, a);
  return m;
}

// ------------------------------------------------------------------ storage
const STORAGE_KEY = "island.keybindings";
const ENDPOINT = "/accounts/keybindings/";

function readLocal(): unknown {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"); } catch { return null; }
}

/** Bindings from localStorage now; the server copy (if signed in) replaces them when it arrives. */
export async function loadBindings(fetchFn: typeof fetch = fetch): Promise<Bindings> {
  try {
    const res = await fetchFn(ENDPOINT, { credentials: "same-origin" });
    if (res.ok) {
      const body = (await res.json()) as { keybindings?: unknown };
      const saved = body.keybindings;
      if (saved && typeof saved === "object" && Object.keys(saved).length) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); } catch { /* storage off */ }
        return mergeBindings(saved);
      }
    }
  } catch { /* offline or signed out: fall back to the local copy */ }
  return mergeBindings(readLocal());
}

/** Save the changed bindings locally and to the account (used by the key settings screen). */
export async function saveBindings(b: Bindings, csrfToken: string, fetchFn: typeof fetch = fetch): Promise<boolean> {
  const diff = diffFromDefaults(b);
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(diff)); } catch { /* storage off */ }
  try {
    const res = await fetchFn(ENDPOINT, {
      method: "PUT", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify({ keybindings: diff }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
