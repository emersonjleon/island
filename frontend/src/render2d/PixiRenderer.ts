// PixiJS 2D renderer. World units are hex radii scaled by UNIT pixels; the camera
// is the transform of the world container, moved by the input package through
// panBy / zoomAt / centerOn.
import { Application, Container, Graphics, Text } from "pixi.js";

import { BoardGeometry, hexCenter, hexCorners, type Pt } from "../board/geometry";
import type { BoardMsg } from "../protocol/types";
import type { Insets, Overlays, PickResult, Renderer } from "../render/Renderer";
import { constructionProgress, settlerPosition } from "../sim/interp";
import type { GameStore } from "../state/store";
import { drawTerrainDecor, drawWaves } from "./decor";
import * as P from "./palette";

const UNIT = 60;
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 4;
const MAX_RESOLUTION = 2;
/** Largest side of the cached board texture, in pixels (safe on phones). */
const MAX_CACHE_PX = 4096;

export class PixiRenderer implements Renderer {
  private app = new Application();
  private world = new Container();
  private boardLayer = new Container();
  private piecesLayer = new Graphics();
  private overlayLayer = new Graphics();
  private progressLayer = new Graphics();
  private settlerLayer = new Graphics();
  private robberLayer = new Graphics();
  private geo: BoardGeometry | null = null;
  private board: BoardMsg | null = null;
  private drawnVersion = -1;
  /** Resolution the static board is cached at (0 = not cached yet). */
  private cacheRes = 0;
  private overlays: Overlays = {};
  private store: GameStore | null = null;
  private lastNow = 0;
  private resizeObserver: ResizeObserver | null = null;
  private fitInsets: () => Insets = () => ({ top: 0, right: 0, bottom: 0, left: 0 });

  async mount(el: HTMLElement): Promise<void> {
    // Phones: no MSAA and at most 2x pixels, which keeps the frame rate up and the battery cool.
    const coarse = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
    // The sea around the board is the page's own gradient behind a transparent canvas.
    await this.app.init({ resizeTo: el, backgroundAlpha: 0, antialias: !coarse, autoDensity: true,
                          resolution: Math.min(window.devicePixelRatio || 1, MAX_RESOLUTION),
                          ...(coarse ? { powerPreference: "low-power" as const } : {}) });
    el.appendChild(this.app.canvas);
    this.keepCentreOnResize(el);
    this.world.addChild(this.boardLayer, this.piecesLayer, this.progressLayer, this.robberLayer,
                        this.overlayLayer, this.settlerLayer);
    this.app.stage.addChild(this.world);
  }

  update(store: GameStore, now: number): void {
    this.store = store;
    this.lastNow = now;
    if (store.board && store.board !== this.board) {
      this.board = store.board;
      this.geo = new BoardGeometry(store.board);
      this.drawBoard();
      this.cacheRes = 0;
      this.fit();
      this.drawnVersion = -1;
    }
    if (!this.geo || !store.state) return;
    if (store.version !== this.drawnVersion) {
      this.drawPieces(store);
      this.drawOverlays();
      this.drawnVersion = store.version;
    }
    this.drawMoving(store, now);
    this.cacheBoard();
  }

  // ------------------------------------------------------------------ board
  private drawBoard(): void {
    const geo = this.geo!;
    const board = this.board!;
    this.boardLayer.removeChildren().forEach((c) => c.destroy());
    const fishing = new Map(board.fishing.map((f) => [f.hex, f.token]));
    const land = board.hexes.filter((h) => h.land && h.terrain);

    // Sea: a faint grid, darker fishing grounds and a few waves.
    const sea = new Graphics();
    for (const h of board.hexes) {
      if (h.land) continue;
      const c = geo.hex[h.id]!;
      const fish = fishing.has(h.id);
      sea.poly(this.hexPts(h.q, h.r, 0.97)).fill({ color: fish ? P.FISHING : P.SEA, alpha: fish ? 0.9 : 0.3 })
        .stroke({ width: 1, color: P.SEA_EDGE, alpha: fish ? 0.9 : 0.35 });
      drawWaves(sea, h.id, c.x * UNIT, c.y * UNIT, UNIT, P.WAVE, fish ? 0.35 : 0.22);
    }
    // Coast: shallow water, then a sandy beach, under every land hex.
    const coast = new Graphics();
    for (const h of land) coast.poly(this.hexPts(h.q, h.r, 1.3)).fill({ color: P.SHALLOWS, alpha: 0.55 });
    for (const h of land) coast.poly(this.hexPts(h.q, h.r, 1.12)).fill(P.SAND);
    for (const h of land) coast.poly(this.hexPts(h.q, h.r, 1.12)).stroke({ width: 1.5, color: P.SAND_EDGE, alpha: 0.6 });
    // Land: each hex with a darker rim, a lighter top and its details.
    const tiles = new Graphics();
    for (const h of land) {
      const terrain = h.terrain!;
      const c = geo.hex[h.id]!;
      tiles.poly(this.hexPts(h.q, h.r, 0.985)).fill(P.TERRAIN_EDGE[terrain]);
      tiles.poly(this.hexPts(h.q, h.r, 0.9)).fill(P.TERRAIN[terrain]);
      tiles.poly(this.hexPts(h.q, h.r, 0.9)).stroke({ width: 2, color: 0xffffff, alpha: 0.18 });
      drawTerrainDecor(tiles, terrain, h.id, c.x * UNIT, c.y * UNIT, UNIT);
    }
    this.boardLayer.addChild(sea, coast, tiles);

    for (const h of board.hexes) {
      const token = h.land ? h.token : fishing.get(h.id) ?? null;
      if (token) this.boardLayer.addChild(this.token(geo.hex[h.id]!, token, !h.land));
    }
    for (const hb of board.harbors) this.boardLayer.addChild(this.harbor(hb.vertices, hb.ratio, hb.resource));
  }

  private hexPts(q: number, r: number, k: number): number[] {
    const c = hexCenter(q, r);
    return hexCorners(q, r).flatMap((p) => [(c.x + (p.x - c.x) * k) * UNIT, (c.y + (p.y - c.y) * k) * UNIT]);
  }

  private token(c: Pt, value: number, fish: boolean): Container {
    const box = new Container();
    box.position.set(c.x * UNIT, c.y * UNIT);
    const red = value === 6 || value === 8;
    const g = new Graphics()
      .circle(UNIT * 0.02, UNIT * 0.035, UNIT * 0.3).fill({ color: P.SHADOW, alpha: 0.3 })
      .circle(0, 0, UNIT * 0.3).fill(P.TOKEN_BG).stroke({ width: 2, color: fish ? P.WAVE : P.TOKEN_RING })
      .circle(0, 0, UNIT * 0.25).stroke({ width: 1, color: P.TOKEN_RING, alpha: 0.5 });
    const label = new Text({ text: String(value), style: { fontFamily: "Georgia, 'Times New Roman', serif", fontSize: UNIT * 0.27,
      fontWeight: "700", fill: red ? P.TOKEN_RED : P.TOKEN_TEXT } });
    label.anchor.set(0.5, 0.62);
    const dots = new Graphics();
    const n = P.pips(value);
    for (let i = 0; i < n; i++) dots.circle((i - (n - 1) / 2) * UNIT * 0.07, UNIT * 0.15, UNIT * 0.025);
    dots.fill(red ? P.TOKEN_RED : P.TOKEN_TEXT);
    box.addChild(g, label, dots);
    if (fish) {
      // A little fish above the token marks a fishing ground.
      const y = -UNIT * 0.45;
      const fishMark = new Graphics()
        .ellipse(0, y, UNIT * 0.09, UNIT * 0.045)
        .poly([UNIT * 0.07, y, UNIT * 0.14, y - UNIT * 0.045, UNIT * 0.14, y + UNIT * 0.045])
        .fill(P.WAVE)
        .circle(-UNIT * 0.045, y - UNIT * 0.01, UNIT * 0.012).fill(P.SEA);
      box.addChild(fishMark);
    }
    return box;
  }

  private harbor(vertices: number[], ratio: number, resource: string | null): Container {
    const geo = this.geo!;
    const a = geo.vertex[vertices[0]!]!;
    const b = geo.vertex[vertices[1]!]!;
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    // Push the marker out to sea: away from the centre of the land hexes next to the edge.
    const out = this.seaward(mid);
    const pos = { x: mid.x + out.x * 0.45, y: mid.y + out.y * 0.45 };
    const box = new Container();
    // Two wooden piers from the shore to the harbour badge.
    const lines = new Graphics();
    for (const end of [a, b]) {
      const s = { x: end.x + (pos.x - end.x) * 0.12, y: end.y + (pos.y - end.y) * 0.12 };
      lines.moveTo(s.x * UNIT, s.y * UNIT).lineTo(pos.x * UNIT, pos.y * UNIT);
    }
    lines.stroke({ width: 6, color: P.PIER_DARK, cap: "round" });
    for (const end of [a, b]) {
      const s = { x: end.x + (pos.x - end.x) * 0.12, y: end.y + (pos.y - end.y) * 0.12 };
      lines.moveTo(s.x * UNIT, s.y * UNIT).lineTo(pos.x * UNIT, pos.y * UNIT);
    }
    lines.stroke({ width: 3.5, color: P.PIER, cap: "round" });
    const colour = resource ? P.RESOURCE[resource as keyof typeof P.RESOURCE] : 0xffffff;
    const badge = new Graphics()
      .circle(pos.x * UNIT + 1.5, pos.y * UNIT + 2.5, UNIT * 0.21).fill({ color: P.SHADOW, alpha: 0.35 })
      .circle(pos.x * UNIT, pos.y * UNIT, UNIT * 0.21).fill(0xffffff).stroke({ width: 1.5, color: P.PIER_DARK })
      .circle(pos.x * UNIT, pos.y * UNIT, UNIT * 0.165).fill(colour);
    const dark = resource === "lumber" || resource === "brick";
    const label = new Text({ text: `${ratio}:1`, style: { fontFamily: "system-ui, sans-serif", fontSize: UNIT * 0.15,
      fontWeight: "800", fill: dark ? 0xffffff : P.TOKEN_TEXT } });
    label.anchor.set(0.5);
    label.position.set(pos.x * UNIT, pos.y * UNIT);
    box.addChild(lines, badge, label);
    return box;
  }

  private seaward(p: Pt): Pt {
    const geo = this.geo!;
    let sx = 0;
    let sy = 0;
    for (const h of this.board!.hexes) {
      if (!h.land) continue;
      const c = geo.hex[h.id]!;
      const d2 = (c.x - p.x) ** 2 + (c.y - p.y) ** 2;
      if (d2 < 1.2) {
        sx += p.x - c.x;
        sy += p.y - c.y;
      }
    }
    const len = Math.hypot(sx, sy) || 1;
    return { x: sx / len, y: sy / len };
  }

  /** The board never changes during a game, so it is drawn once into a texture and
   * re-cached only when the zoom moves far enough to make it look soft. Drawing all
   * the sea, beaches and details every frame is too slow on weak phones. */
  private cacheBoard(): void {
    const b = this.boardLayer.getLocalBounds();
    const side = Math.max(b.width, b.height, 1);
    const want = this.world.scale.x * this.app.renderer.resolution;
    // Steps of √2 so small zooms don't re-cache; never larger than the texture limit.
    const step = Math.SQRT2 ** Math.ceil(Math.log(Math.max(want, 0.25)) / Math.log(Math.SQRT2));
    const res = Math.min(step, MAX_CACHE_PX / side);
    if (Math.abs(res - this.cacheRes) < 1e-6) return;
    this.cacheRes = res;
    this.boardLayer.cacheAsTexture(false);
    this.boardLayer.cacheAsTexture({ resolution: res, antialias: true });
  }

  // ------------------------------------------------------------------ pieces
  private drawPieces(store: GameStore): void {
    const geo = this.geo!;
    const s = store.state!;
    const g = this.piecesLayer.clear();
    for (const road of s.roads) this.road(g, road.edge, P.playerColour(store.colourOf(road.seat)), 1);
    for (const c of s.constructions) {
      if (c.kind === "road") this.road(g, c.target, P.playerColour(store.colourOf(c.seat)), 0.35);
    }
    for (const b of s.buildings) this.building(g, geo.vertex[b.vertex]!, b.kind, P.playerColour(store.colourOf(b.seat)), 1);
    for (const c of s.constructions) {
      if (c.kind !== "road") this.building(g, geo.vertex[c.target]!, c.kind, P.playerColour(store.colourOf(c.seat)), 0.35);
    }
    const r = this.robberLayer.clear();
    if (s.robber !== null && geo.hex[s.robber]) {
      const c = geo.hex[s.robber]!;
      const x = c.x * UNIT + UNIT * 0.42;
      const y = c.y * UNIT;
      r.ellipse(x + 2, y + UNIT * 0.2, UNIT * 0.13, UNIT * 0.04).fill({ color: P.SHADOW, alpha: 0.4 });
      r.poly([x - UNIT * 0.11, y + UNIT * 0.19, x - UNIT * 0.06, y - UNIT * 0.04, x + UNIT * 0.06, y - UNIT * 0.04, x + UNIT * 0.11, y + UNIT * 0.19])
        .circle(x, y - UNIT * 0.1, UNIT * 0.075).fill(0x2a2a2e).stroke({ width: 1.5, color: 0xe8e2d0 });
    }
  }

  private road(g: Graphics, edge: number, colour: number, alpha: number): void {
    const [a, b] = this.geo!.edgeEnds(edge);
    const t = 0.18;
    const a2 = { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    const b2 = { x: b.x + (a.x - b.x) * t, y: b.y + (a.y - b.y) * t };
    const line = (dx: number, dy: number) => g.moveTo(a2.x * UNIT + dx, a2.y * UNIT + dy).lineTo(b2.x * UNIT + dx, b2.y * UNIT + dy);
    line(1.5, 2.5).stroke({ width: 10, color: P.SHADOW, alpha: 0.3 * alpha, cap: "round" });
    line(0, 0).stroke({ width: 10, color: P.OUTLINE, alpha, cap: "round" });
    line(0, 0).stroke({ width: 7, color: colour, alpha, cap: "round" });
    line(0, -1.5).stroke({ width: 2, color: 0xffffff, alpha: 0.3 * alpha, cap: "round" });
  }

  private building(g: Graphics, p: Pt, kind: string, colour: number, alpha: number): void {
    const x = p.x * UNIT;
    const y = p.y * UNIT;
    const s = UNIT * (kind === "settlement" ? 0.16 : kind === "city" ? 0.2 : 0.25);
    const shape = kind === "settlement"
      ? [x - s, y + s, x - s, y - s * 0.3, x, y - s * 1.2, x + s, y - s * 0.3, x + s, y + s]
      // city / megacity: a house with a tower
      : [x - s * 1.3, y + s, x - s * 1.3, y - s * 0.2, x - s * 0.2, y - s * 0.2, x - s * 0.2, y - s,
         x + s * 0.45, y - s * 1.6, x + s * 1.1, y - s, x + s * 1.1, y + s];
    g.ellipse(x + s * 0.15, y + s * 1.05, s * 1.35, s * 0.35).fill({ color: P.SHADOW, alpha: 0.35 * alpha });
    g.poly(shape).fill({ color: colour, alpha }).stroke({ width: 2, color: P.OUTLINE, alpha, join: "round" });
    // Shade the right-hand side and add a door, so pieces read as little houses.
    const roofX = kind === "settlement" ? x : x + s * 0.45;
    const roofY = kind === "settlement" ? y - s * 1.2 : y - s * 1.6;
    const rightX = kind === "settlement" ? x + s : x + s * 1.1;
    g.poly([roofX, roofY, rightX, kind === "settlement" ? y - s * 0.3 : y - s, rightX, y + s, roofX, y + s])
      .fill({ color: 0x000000, alpha: 0.18 * alpha });
    const doorX = kind === "settlement" ? x - s * 0.5 : x - s * 0.95;
    g.rect(doorX, y + s * 0.2, s * 0.4, s * 0.8).fill({ color: P.OUTLINE, alpha: 0.75 * alpha });
    if (kind === "megacity") g.circle(x, y - s * 1.9, s * 0.35).fill({ color: 0xffd54f, alpha }).stroke({ width: 1.5, color: P.OUTLINE, alpha });
  }

  private drawOverlays(): void {
    const geo = this.geo!;
    const g = this.overlayLayer.clear();
    for (const v of this.overlays.vertices ?? []) {
      const p = geo.vertex[v];
      if (p) g.circle(p.x * UNIT, p.y * UNIT, UNIT * 0.12).stroke({ width: 3, color: P.HIGHLIGHT });
    }
    for (const e of this.overlays.edges ?? []) {
      const [a, b] = geo.edgeEnds(e);
      g.moveTo(a.x * UNIT, a.y * UNIT).lineTo(b.x * UNIT, b.y * UNIT).stroke({ width: 4, color: P.HIGHLIGHT, alpha: 0.8 });
    }
    const fv = this.overlays.focusVertex;
    const fp = fv == null ? undefined : geo.vertex[fv];
    if (fp) g.circle(fp.x * UNIT, fp.y * UNIT, UNIT * 0.2).fill({ color: P.HIGHLIGHT, alpha: 0.45 }).stroke({ width: 4, color: P.HIGHLIGHT });
    const fe = this.overlays.focusEdge;
    if (fe != null && geo.edgeMid[fe]) {
      const [a, b] = geo.edgeEnds(fe);
      g.moveTo(a.x * UNIT, a.y * UNIT).lineTo(b.x * UNIT, b.y * UNIT).stroke({ width: 9, color: P.HIGHLIGHT });
    }
  }

  // ------------------------------------------------------------------ per frame
  private drawMoving(store: GameStore, now: number): void {
    const geo = this.geo!;
    const s = store.state!;
    const prog = this.progressLayer.clear();
    for (const c of s.constructions) {
      const p = c.kind === "road" ? geo.edgeMid[c.target] : geo.vertex[c.target];
      if (!p) continue;
      const w = UNIT * 0.5;
      const x = p.x * UNIT - w / 2;
      const y = p.y * UNIT + UNIT * 0.22;
      prog.roundRect(x - 1.5, y - 1.5, w + 3, 9, 4.5).fill({ color: P.OUTLINE, alpha: 0.85 })
        .roundRect(x, y, Math.max(6, w * constructionProgress(c, now)), 6, 3).fill(P.playerColour(store.colourOf(c.seat)));
    }
    const g = this.settlerLayer.clear();
    for (const settler of s.settlers) {
      const p = settlerPosition(geo, settler, now);
      const colour = P.playerColour(store.colourOf(settler.seat));
      const selected = this.overlays.selectedSettlers?.includes(settler.id) ?? false;
      const x = p.x * UNIT;
      const y = p.y * UNIT;
      if (selected) g.circle(x, y, UNIT * 0.24).fill({ color: P.HIGHLIGHT, alpha: 0.35 });
      g.ellipse(x + 2, y + UNIT * 0.14, UNIT * 0.15, UNIT * 0.05).fill({ color: P.SHADOW, alpha: 0.4 });
      g.circle(x, y, UNIT * 0.16).fill(colour).stroke({ width: selected ? 4 : 2, color: selected ? P.HIGHLIGHT : P.OUTLINE });
      g.circle(x - UNIT * 0.05, y - UNIT * 0.06, UNIT * 0.05).fill({ color: 0xffffff, alpha: 0.35 });
      // A tiny figure on the token: head and shoulders.
      g.circle(x, y - UNIT * 0.05, UNIT * 0.045).fill(P.OUTLINE);
      g.ellipse(x, y + UNIT * 0.05, UNIT * 0.075, UNIT * 0.045).fill(P.OUTLINE);
      if (settler.path.length) {
        let prev = settler.step ? geo.vertex[settler.step.to_v]! : p;
        for (const v of settler.path) {
          const q = geo.vertex[v]!;
          g.moveTo(prev.x * UNIT, prev.y * UNIT).lineTo(q.x * UNIT, q.y * UNIT);
          prev = q;
        }
        g.stroke({ width: 2, color: colour, alpha: 0.7 });
      }
    }
  }

  // ------------------------------------------------------------------ camera
  /** Phones resize the page all the time (address bar, keyboard, rotation): keep the
   * point at the centre of the screen where it was instead of refitting the island. */
  private keepCentreOnResize(el: HTMLElement): void {
    if (typeof ResizeObserver !== "function") return;
    let w = this.app.screen.width;
    let h = this.app.screen.height;
    this.resizeObserver = new ResizeObserver(() => {
      this.app.resize();
      const nw = this.app.screen.width;
      const nh = this.app.screen.height;
      if (nw === w && nh === h) return;
      // A turned phone gets the whole island again; other resizes keep the camera where it was.
      if (w > 0 && h > 0 && (nw > nh) !== (w > h)) this.fit();
      else this.panBy((nw - w) / 2, (nh - h) / 2);
      w = nw;
      h = nh;
    });
    this.resizeObserver.observe(el);
  }

  setFitInsets(fn: () => Insets): void {
    this.fitInsets = fn;
  }

  fit(): void {
    if (!this.geo) return;
    const { minX, minY, maxX, maxY } = this.islandBounds();
    const sw = this.app.screen.width;
    const sh = this.app.screen.height;
    // Fit into the part of the screen the HUD leaves free, unless that is too small to be useful.
    let ins = this.fitInsets();
    if (sw - ins.left - ins.right < sw * 0.5 || sh - ins.top - ins.bottom < sh * 0.4) ins = { top: 0, right: 0, bottom: 0, left: 0 };
    const w = sw - ins.left - ins.right;
    const h = sh - ins.top - ins.bottom;
    const scale = Math.min(w / ((maxX - minX) * UNIT), h / ((maxY - minY) * UNIT)) * 0.95;
    this.world.scale.set(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, scale)));
    const s = this.world.scale.x;
    this.world.position.set(ins.left + w / 2 - ((minX + maxX) / 2) * UNIT * s, ins.top + h / 2 - ((minY + maxY) / 2) * UNIT * s);
  }

  /** Land and fishing grounds (plus a hex radius): open sea around them is not worth screen space. */
  private islandBounds(): { minX: number; minY: number; maxX: number; maxY: number } {
    const geo = this.geo!;
    const fishing = new Set(this.board!.fishing.map((f) => f.hex));
    const pts = this.board!.hexes.filter((h) => h.land || fishing.has(h.id)).map((h) => geo.hex[h.id]!);
    if (!pts.length) return geo.bounds;
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    return { minX: Math.min(...xs) - 1, minY: Math.min(...ys) - 1, maxX: Math.max(...xs) + 1, maxY: Math.max(...ys) + 1 };
  }

  screenToWorld(sx: number, sy: number): Pt {
    const p = this.world.toLocal({ x: sx, y: sy });
    return { x: p.x / UNIT, y: p.y / UNIT };
  }

  pick(sx: number, sy: number, slopPx = 0): PickResult {
    if (!this.geo) return null;
    const w = this.screenToWorld(sx, sy);
    const now = this.lastNow;
    // A finger's slop in world units; vertices stay tighter so edges remain reachable.
    const slop = slopPx / (UNIT * this.world.scale.x);
    const settlerR = Math.max(0.2, slop);
    let best: { id: number; d2: number } | null = null;
    for (const s of this.store?.state?.settlers ?? []) {
      const p = settlerPosition(this.geo, s, now);
      const d2 = (p.x - w.x) ** 2 + (p.y - w.y) ** 2;
      if (d2 < settlerR ** 2 && (!best || d2 < best.d2)) best = { id: s.id, d2 };
    }
    if (best) return { kind: "settler", id: best.id };
    const v = this.geo.nearestVertex(w, Math.max(0.3, Math.min(slop, 0.38)));
    if (v !== null) return { kind: "vertex", id: v };
    const e = this.geo.nearestEdge(w, Math.max(0.3, slop));
    if (e !== null) return { kind: "edge", id: e };
    const h = this.geo.nearestHex(w, 0.9);
    return h !== null ? { kind: "hex", id: h } : null;
  }

  setOverlays(opts: Overlays): void {
    this.overlays = opts;
    this.drawnVersion = -1;
  }

  worldToScreen(p: Pt): Pt {
    const g = this.world.toGlobal({ x: p.x * UNIT, y: p.y * UNIT });
    return { x: g.x, y: g.y };
  }

  panBy(dx: number, dy: number): void {
    this.world.position.x += dx;
    this.world.position.y += dy;
  }

  zoomAt(factor: number, sx: number, sy: number): void {
    const before = this.world.toLocal({ x: sx, y: sy });
    this.world.scale.set(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.world.scale.x * factor)));
    const after = this.world.toGlobal(before);
    this.panBy(sx - after.x, sy - after.y);
  }

  centerOn(p: Pt): void {
    const s = this.worldToScreen(p);
    this.panBy(this.app.screen.width / 2 - s.x, this.app.screen.height / 2 - s.y);
  }

  destroy(): void {
    this.resizeObserver?.disconnect();
    this.app.destroy(true, { children: true });
  }
}
