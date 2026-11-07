import { describe, expect, it } from "vitest";

import { ACTIONS, DEFAULT_BINDINGS, comboOf, conflicts, diffFromDefaults, keymap, mergeBindings, normaliseCombo } from "./bindings";

const key = (code: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  ({ code, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("key bindings", () => {
  it("defaults bind every action and have no conflicts", () => {
    for (const a of ACTIONS) expect(DEFAULT_BINDINGS[a].length).toBeGreaterThan(0);
    expect(conflicts(DEFAULT_BINDINGS).size).toBe(0);
  });

  it("builds combos with modifiers in a fixed order", () => {
    expect(comboOf(key("KeyW"))).toBe("KeyW");
    expect(comboOf(key("KeyW", { shiftKey: true, ctrlKey: true }))).toBe("Ctrl+Shift+KeyW");
    expect(normaliseCombo("Shift+Ctrl+KeyW")).toBe("Ctrl+Shift+KeyW");
  });

  it("separates walking from camera moves by Shift", () => {
    const m = keymap(DEFAULT_BINDINGS);
    expect(m.get("KeyW")).toBe("move_up");
    expect(m.get("Shift+KeyW")).toBe("camera_up");
    expect(m.get("ArrowLeft")).toBe("move_left");
  });

  it("merges saved bindings over defaults and drops junk", () => {
    const b = mergeBindings({ move_up: ["KeyI"], nonsense: ["KeyX"], move_down: "KeyK", zoom_in: [3, "Shift+Ctrl+KeyZ"] });
    expect(b.move_up).toEqual(["KeyI"]);
    expect(b.move_down).toEqual(DEFAULT_BINDINGS.move_down);
    expect(b.zoom_in).toEqual(["Ctrl+Shift+KeyZ"]);
    expect(diffFromDefaults(b)).toEqual({ move_up: ["KeyI"], zoom_in: ["Ctrl+Shift+KeyZ"] });
    expect(mergeBindings(null)).toEqual(DEFAULT_BINDINGS);
  });

  it("reports conflicts", () => {
    const b = mergeBindings({ build_road: ["KeyW"] });
    expect(conflicts(b).get("KeyW")).toEqual(["move_up", "build_road"]);
  });
});
