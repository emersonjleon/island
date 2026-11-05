// What every renderer (2D now, three.js later) implements. Renderers read the
// store and the clock; they never change game state.
import type { Pt } from "../board/geometry";
import type { GameStore } from "../state/store";

export type PickResult =
  | { kind: "vertex"; id: number }
  | { kind: "edge"; id: number }
  | { kind: "hex"; id: number }
  | { kind: "settler"; id: number }
  | null;

export interface Overlays {
  /** Highlight these vertices / edges (e.g. buildable spots in build mode). */
  vertices?: number[];
  edges?: number[];
  selectedSettler?: number | null;
}

export interface Renderer {
  mount(el: HTMLElement): Promise<void>;
  /** Called every frame with the estimated server time. */
  update(store: GameStore, now: number): void;
  pick(screenX: number, screenY: number): PickResult;
  screenToWorld(screenX: number, screenY: number): Pt;
  fit(): void;
  setOverlays(opts: Overlays): void;
  destroy(): void;
}
