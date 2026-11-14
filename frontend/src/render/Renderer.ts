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
  /** The one candidate the player is about to choose (drawn stronger). */
  focusVertex?: number | null;
  focusEdge?: number | null;
  /** Robber mode (knight card): hexes it may go to, and the one about to be chosen. */
  hexes?: number[];
  focusHex?: number | null;
  selectedSettlers?: number[];
}

/** Screen pixels covered by HUD panels on each side; fit() keeps the island clear of them. */
export interface Insets { top: number; right: number; bottom: number; left: number }

export interface Renderer {
  mount(el: HTMLElement): Promise<void>;
  /** Called every frame with the estimated server time. */
  update(store: GameStore, now: number): void;
  /** What is under a screen point; ``slopPx`` widens the hit area (for fingers). */
  pick(screenX: number, screenY: number, slopPx?: number): PickResult;
  screenToWorld(screenX: number, screenY: number): Pt;
  worldToScreen(p: Pt): Pt;
  /** Camera: screen-pixel pan, zoom by a factor around a screen point, centre on a world point. */
  panBy(dx: number, dy: number): void;
  zoomAt(factor: number, screenX: number, screenY: number): void;
  centerOn(p: Pt): void;
  fit(): void;
  /** Where the HUD covers the screen, asked for each time the camera fits the island. */
  setFitInsets?(fn: () => Insets): void;
  setOverlays(opts: Overlays): void;
  destroy(): void;
}
