import { describe, expect, it } from "vitest";

import { BoardGeometry, walkableNeighbours, type Pt } from "../board/geometry";
import type { BoardMsg, GameStateView, Intent, SettlerView } from "../protocol/types";
import type { Overlays, PickResult, Renderer } from "../render/Renderer";
import { GameStore } from "../state/store";
import { fixture } from "../testing/fixtures";
import { DEFAULT_BINDINGS } from "./bindings";
import { InputController, type MenuItem } from "./controller";

const UNIT = 60;

class FakeRenderer implements Renderer {
  pans: Pt[] = [];
  overlays: Overlays = {};
  nextPick: PickResult = null;
  async mount(): Promise<void> {}
  update(): void {}
  pick(): PickResult { return this.nextPick; }
  screenToWorld(x: number, y: number): Pt { return { x: x / UNIT, y: y / UNIT }; }
  worldToScreen(p: Pt): Pt { return { x: p.x * UNIT, y: p.y * UNIT }; }
  panBy(dx: number, dy: number): void { this.pans.push({ x: dx, y: dy }); }
  zoomAt(): void {}
  centerOn(): void {}
  fit(): void {}
  setOverlays(o: Overlays): void { this.overlays = o; }
  destroy(): void {}
}

function setup(phase: GameStateView["phase"] = "setup") {
  const board = fixture<BoardMsg>("board.json");
  const geo = new BoardGeometry(board);
  const start = board.vertices.find((v) => walkableNeighbours(board, v.id).length === 3)!.id;
  const store = new GameStore();
  store.board = board;
  store.seat = 0;
  const settler: SettlerView = { id: 7, seat: 0, vertex: start, path: [], step: null };
  store.state = {
    phase, now: 0, viewer: 0, bank: {}, buildings: [], roads: [], constructions: [], robber: null,
    clock_started: phase !== "setup", next_roll_at: null, last_roll: null, dice_history: [], winner: null, finished_at: null,
    players: [{ seat: 0, name: "ana", colour: "red", pieces: {}, setup: { remaining: {}, done: false, settlements_built: 0 }, settlers: [7] }],
    settlers: [settler, { id: 8, seat: 1, vertex: start, path: [], step: null }],
    buildable: { roads: [], settlements: [], cities: [] },
  };
  const sent: Intent[] = [];
  const renderer = new FakeRenderer();
  let now = 1000;
  const menus: MenuItem[][] = [];
  const input = new InputController({
    store, renderer, bindings: DEFAULT_BINDINGS, now: () => now,
    send: (i) => { sent.push(i); return `c${sent.length}`; },
    showMenu: (_x, _y, items) => { menus.push(items); return () => {}; },
  });
  input.tick(16);
  return { board, geo, store, settler, sent, renderer, input, menus, start, setNow: (t: number) => (now = t) };
}

describe("InputController", () => {
  it("selects the player's own settler, never someone else's", () => {
    const { input, renderer } = setup();
    expect(input.selected).toEqual([7]);
    expect(renderer.overlays.selectedSettlers).toEqual([7]);
  });

  it("walks one step per key press toward the pressed direction", () => {
    const { input, sent, geo, start } = setup();
    input.action("move_up");
    expect(sent).toHaveLength(1);
    const m = sent[0] as Extract<Intent, { a: "move_settler" }>;
    expect(m).toMatchObject({ a: "move_settler", settler: 7, mode: "append" });
    expect(geo.vertex[m.to_vertex]!.y).toBeLessThan(geo.vertex[start]!.y);
    // No second order until the server confirms the first.
    input.tick(16);
    expect(sent).toHaveLength(1);
  });

  it("keeps walking while the key is held, queuing as each step ends", () => {
    const { input, sent, settler, setNow, start } = setup();
    input.action("move_up");
    const first = (sent[0] as Extract<Intent, { a: "move_settler" }>).to_vertex;
    // Server starts the step: 1000 -> 2500.
    settler.step = { edge: 0, from_v: start, to_v: first, t0: 1000, t1: 2500 };
    setNow(1100);
    input.tick(16);
    expect(sent).toHaveLength(1);          // too early
    setNow(2100);
    input.tick(16);
    expect(sent).toHaveLength(2);          // last 35 % of the step
    expect(sent[1]).toMatchObject({ a: "move_settler", settler: 7, mode: "append" });
    expect((sent[1] as Extract<Intent, { a: "move_settler" }>).to_vertex).not.toBe(start);
  });

  it("stops queuing when the key is released", () => {
    const { input, sent, settler, setNow, start } = setup();
    input.action("move_up");
    const first = (sent[0] as Extract<Intent, { a: "move_settler" }>).to_vertex;
    settler.step = { edge: 0, from_v: start, to_v: first, t0: 1000, t1: 2500 };
    (input as unknown as { keyUp(e: { code: string }): void }).keyUp({ code: "KeyW" });
    setNow(2400);
    input.tick(16);
    expect(sent).toHaveLength(1);
  });

  it("build mode walks the settler to the spot, then builds when it arrives", () => {
    const { input, sent, settler, store, board, start } = setup();
    const target = walkableNeighbours(board, walkableNeighbours(board, start)[0]!)
      .find((v) => v !== start)!;
    store.state!.buildable = { roads: [], settlements: [target], cities: [] };
    input.action("build_settlement");
    expect(input.mode).toEqual({ kind: "settlement", focus: target });
    input.action("confirm");
    expect(input.mode).toBeNull();
    expect(sent[0]).toEqual({ a: "move_settler", settler: 7, to_vertex: target, mode: "replace" });
    input.tick(16);
    expect(sent).toHaveLength(1);
    settler.vertex = target;               // arrived
    input.tick(16);
    expect(sent[1]).toEqual({ a: "build", kind: "settlement", vertex: target, settler: 7 });
    input.tick(16);
    expect(sent).toHaveLength(2);
  });

  it("builds at once when the settler already stands on the spot", () => {
    const { input, sent, store, start } = setup();
    store.state!.buildable = { roads: [], settlements: [start], cities: [] };
    input.action("build_settlement");
    input.action("confirm");
    expect(sent).toEqual([{ a: "build", kind: "settlement", vertex: start, settler: 7 }]);
  });

  it("roads can be built from either end of the edge", () => {
    const { input, sent, store, board, start } = setup();
    const edge = board.vertices[start]!.adj_e.find((e) => board.edges[e]!.hexes.some((h) => board.hexes[h]!.land))!;
    store.state!.buildable = { roads: [edge], settlements: [], cities: [] };
    input.action("build_road");
    input.action("confirm");
    expect(sent).toEqual([{ a: "build", kind: "road", edge, settler: 7 }]);
  });

  it("after setup, builds without a settler unless the game requires one", () => {
    const { input, sent, store } = setup("running");
    store.state!.players[0]!.setup.done = true;
    store.state!.buildable = { roads: [], settlements: [], cities: [3] };
    input.action("build_city");
    input.action("confirm");
    expect(sent).toEqual([{ a: "build", kind: "city", vertex: 3 }]);
  });

  it("build mode follows candidates that appear while it is open", () => {
    const { input, store, start } = setup();
    const modes: (number | null)[] = [];
    (input as unknown as { opts: { onMode: (m: { count: number } | null) => void } }).opts.onMode = (m) => modes.push(m && m.count);
    input.action("build_settlement");
    expect(input.mode!.focus).toBeNull();
    store.state!.buildable = { roads: [], settlements: [start], cities: [] };
    input.tick(16);
    expect(input.mode!.focus).toBe(start);
    expect(modes).toEqual([0, 1]);
  });

  it("still walks a builder for setup pieces after the dice clock has started", () => {
    const { input, sent, store, board, start } = setup("running");
    const target = walkableNeighbours(board, walkableNeighbours(board, start)[0]!).find((v) => v !== start)!;
    store.state!.buildable = { roads: [], settlements: [target], cities: [] };
    input.action("build_settlement");
    input.action("confirm");
    expect(sent).toEqual([{ a: "move_settler", settler: 7, to_vertex: target, mode: "replace" }]);
  });

    it("Tab cycles build candidates and Esc leaves build mode", () => {
    const { input, store } = setup();
    store.state!.buildable = { roads: [], settlements: [3, 40, 90], cities: [] };
    input.action("build_settlement");
    const seen = new Set<number | null>();
    for (let i = 0; i < 3; i++) { seen.add(input.mode!.focus); input.action("select_next"); }
    expect(seen).toEqual(new Set([3, 40, 90]));
    input.action("cancel");
    expect(input.mode).toBeNull();
  });

  it("right-click walks, or offers a menu when something can be built there", () => {
    const { input, sent, renderer, menus, store, start } = setup();
    const target = start;
    const call = (input as unknown as { rightClick(p: Pt, shift: boolean): void });
    renderer.nextPick = { kind: "vertex", id: target };
    call.rightClick({ x: 0, y: 0 }, false);
    expect(sent).toEqual([{ a: "move_settler", settler: 7, to_vertex: target, mode: "replace" }]);
    store.state!.buildable = { roads: [], settlements: [target], cities: [] };
    call.rightClick({ x: 0, y: 0 }, false);
    expect(menus[0]!.map((m) => m.label)).toEqual(["walk", "settlement"]);
  });

  it("a rejected move frees the settler for new orders", () => {
    const { input, sent } = setup();
    input.action("move_up");
    input.rejected(sent[0]);
    (input as unknown as { held: Set<string> }).held.add("move_up");
    input.tick(16);
    expect(sent).toHaveLength(2);
  });

  it("Shift+WASD pans the camera instead of walking", () => {
    const { input, sent, renderer } = setup();
    input.action("camera_left");
    input.tick(100);
    expect(sent).toHaveLength(0);
    expect(renderer.pans.at(-1)!.x).toBeGreaterThan(0);
  });

  it("spectators cannot give orders", () => {
    const { input, sent, store } = setup();
    store.seat = null;
    input.tick(16);
    input.action("move_up");
    expect(sent).toHaveLength(0);
  });
});
