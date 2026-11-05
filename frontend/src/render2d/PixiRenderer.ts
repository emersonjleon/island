// PixiJS 2D renderer. World units are hex radii scaled by UNIT pixels; the camera
// is the transform of the world container (drag to pan, wheel to zoom).
import { Application, Container, Graphics, Text } from "pixi.js";

import { BoardGeometry, hexCorners, type Pt } from "../board/geometry";
import type { BoardMsg } from "../protocol/types";
import type { Overlays, PickResult, Renderer } from "../render/Renderer";
import { constructionProgress, settlerPosition } from "../sim/interp";
import type { GameStore } from "../state/store";
import * as P from "./palette";

const UNIT = 60;
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 4;

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
  private overlays: Overlays = {};
  private store: GameStore | null = null;
  private dragging: { x: number; y: number } | null = null;
  private lastNow = 0;

  async mount(el: HTMLElement): Promise<void> {
    await this.app.init({ resizeTo: el, background: P.SEA, antialias: true, autoDensity: true,
                          resolution: window.devicePixelRatio || 1 });
    el.appendChild(this.app.canvas);
    this.world.addChild(this.boardLayer, this.piecesLayer, this.progressLayer, this.robberLayer,
                        this.overlayLayer, this.settlerLayer);
    this.app.stage.addChild(this.world);
    this.bindCamera(this.app.canvas);
  }

  update(store: GameStore, now: number): void {
    this.store = store;
    this.lastNow = now;
    if (store.board && store.board !== this.board) {
      this.board = store.board;
      this.geo = new BoardGeometry(store.board);
      this.drawBoard();
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
  }

  // ------------------------------------------------------------------ board
  private drawBoard(): void {
    const geo = this.geo!;
    const board = this.board!;
    this.boardLayer.removeChildren().forEach((c) => c.destroy());
    const tiles = new Graphics();
    const fishing = new Map(board.fishing.map((f) => [f.hex, f.token]));
    for (const h of board.hexes) {
      const pts = hexCorners(h.q, h.r).flatMap((p) => [p.x * UNIT, p.y * UNIT]);
      const fill = h.land && h.terrain ? P.TERRAIN[h.terrain] : fishing.has(h.id) ? P.FISHING : P.SEA;
      tiles.poly(pts).fill(fill).stroke({ width: h.land ? 2 : 1, color: h.land ? P.OUTLINE : P.SEA_EDGE });
    }
    this.boardLayer.addChild(tiles);

    for (const h of board.hexes) {
      const token = h.land ? h.token : fishing.get(h.id) ?? null;
      if (token) this.boardLayer.addChild(this.token(geo.hex[h.id]!, token, !h.land));
    }
    for (const hb of board.harbors) this.boardLayer.addChild(this.harbor(hb.vertices, hb.ratio, hb.resource));
  }

  private token(c: Pt, value: number, fish: boolean): Container {
    const box = new Container();
    box.position.set(c.x * UNIT, c.y * UNIT);
    const red = value === 6 || value === 8;
    const g = new Graphics().circle(0, 0, UNIT * 0.3).fill(P.TOKEN_BG).stroke({ width: 1.5, color: fish ? P.FISHING : P.OUTLINE });
    const label = new Text({ text: String(value), style: { fontFamily: "system-ui, sans-serif", fontSize: UNIT * 0.26,
      fontWeight: "700", fill: red ? P.TOKEN_RED : P.TOKEN_TEXT } });
    label.anchor.set(0.5, 0.62);
    const dots = new Graphics();
    const n = P.pips(value);
    for (let i = 0; i < n; i++) dots.circle((i - (n - 1) / 2) * UNIT * 0.07, UNIT * 0.15, UNIT * 0.025);
    dots.fill(red ? P.TOKEN_RED : P.TOKEN_TEXT);
    box.addChild(g, label, dots);
    if (fish) {
      const fishMark = new Text({ text: "🐟", style: { fontSize: UNIT * 0.22 } });
      fishMark.anchor.set(0.5);
      fishMark.position.set(0, -UNIT * 0.45);
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
    const lines = new Graphics()
      .moveTo(a.x * UNIT, a.y * UNIT).lineTo(pos.x * UNIT, pos.y * UNIT)
      .moveTo(b.x * UNIT, b.y * UNIT).lineTo(pos.x * UNIT, pos.y * UNIT)
      .stroke({ width: 3, color: 0x6d4c2f });
    const colour = resource ? P.RESOURCE[resource as keyof typeof P.RESOURCE] : 0xffffff;
    const badge = new Graphics().circle(pos.x * UNIT, pos.y * UNIT, UNIT * 0.2).fill(colour).stroke({ width: 1.5, color: P.OUTLINE });
    const label = new Text({ text: `${ratio}:1`, style: { fontFamily: "system-ui, sans-serif", fontSize: UNIT * 0.16,
      fontWeight: "700", fill: P.TOKEN_TEXT } });
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
      r.ellipse(c.x * UNIT + UNIT * 0.42, c.y * UNIT, UNIT * 0.11, UNIT * 0.2).fill(0x222222).stroke({ width: 1, color: 0xffffff });
    }
  }

  private road(g: Graphics, edge: number, colour: number, alpha: number): void {
    const [a, b] = this.geo!.edgeEnds(edge);
    const t = 0.18;
    const a2 = { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    const b2 = { x: b.x + (a.x - b.x) * t, y: b.y + (a.y - b.y) * t };
    g.moveTo(a2.x * UNIT, a2.y * UNIT).lineTo(b2.x * UNIT, b2.y * UNIT).stroke({ width: 9, color: P.OUTLINE, alpha, cap: "round" });
    g.moveTo(a2.x * UNIT, a2.y * UNIT).lineTo(b2.x * UNIT, b2.y * UNIT).stroke({ width: 6, color: colour, alpha, cap: "round" });
  }

  private building(g: Graphics, p: Pt, kind: string, colour: number, alpha: number): void {
    const x = p.x * UNIT;
    const y = p.y * UNIT;
    const s = UNIT * (kind === "settlement" ? 0.15 : kind === "city" ? 0.2 : 0.25);
    if (kind === "settlement") {
      g.poly([x - s, y + s, x - s, y - s * 0.3, x, y - s * 1.2, x + s, y - s * 0.3, x + s, y + s]);
    } else {
      // city / megacity: a house with a tower
      g.poly([x - s * 1.3, y + s, x - s * 1.3, y - s * 0.2, x - s * 0.2, y - s * 0.2, x - s * 0.2, y - s,
              x + s * 0.45, y - s * 1.6, x + s * 1.1, y - s, x + s * 1.1, y + s]);
    }
    g.fill({ color: colour, alpha }).stroke({ width: 2, color: P.OUTLINE, alpha });
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
      prog.rect(x, y, w, 6).fill(0x000000).rect(x, y, w * constructionProgress(c, now), 6)
        .fill(P.playerColour(store.colourOf(c.seat)));
    }
    const g = this.settlerLayer.clear();
    for (const settler of s.settlers) {
      const p = settlerPosition(geo, settler, now);
      const colour = P.playerColour(store.colourOf(settler.seat));
      const selected = this.overlays.selectedSettler === settler.id;
      g.circle(p.x * UNIT, p.y * UNIT, UNIT * 0.16).fill(colour).stroke({ width: selected ? 4 : 2, color: selected ? P.HIGHLIGHT : P.OUTLINE });
      g.circle(p.x * UNIT, p.y * UNIT - UNIT * 0.05, UNIT * 0.06).fill(P.OUTLINE);
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
  fit(): void {
    if (!this.geo) return;
    const { minX, minY, maxX, maxY } = this.geo.bounds;
    const w = this.app.screen.width;
    const h = this.app.screen.height;
    const scale = Math.min(w / ((maxX - minX) * UNIT), h / ((maxY - minY) * UNIT)) * 0.95;
    this.world.scale.set(scale);
    this.world.position.set(w / 2 - ((minX + maxX) / 2) * UNIT * scale, h / 2 - ((minY + maxY) / 2) * UNIT * scale);
  }

  screenToWorld(sx: number, sy: number): Pt {
    const p = this.world.toLocal({ x: sx, y: sy });
    return { x: p.x / UNIT, y: p.y / UNIT };
  }

  pick(sx: number, sy: number): PickResult {
    if (!this.geo) return null;
    const w = this.screenToWorld(sx, sy);
    const now = this.lastNow;
    for (const s of this.store?.state?.settlers ?? []) {
      const p = settlerPosition(this.geo, s, now);
      if ((p.x - w.x) ** 2 + (p.y - w.y) ** 2 < 0.2 ** 2) return { kind: "settler", id: s.id };
    }
    const v = this.geo.nearestVertex(w, 0.3);
    if (v !== null) return { kind: "vertex", id: v };
    const e = this.geo.nearestEdge(w, 0.3);
    if (e !== null) return { kind: "edge", id: e };
    const h = this.geo.nearestHex(w, 0.9);
    return h !== null ? { kind: "hex", id: h } : null;
  }

  setOverlays(opts: Overlays): void {
    this.overlays = opts;
    this.drawnVersion = -1;
  }

  private bindCamera(canvas: HTMLCanvasElement): void {
    canvas.addEventListener("pointerdown", (e) => {
      if (e.button === 0 || e.button === 1) this.dragging = { x: e.clientX, y: e.clientY };
    });
    window.addEventListener("pointerup", () => (this.dragging = null));
    window.addEventListener("pointermove", (e) => {
      if (!this.dragging) return;
      this.world.position.x += e.clientX - this.dragging.x;
      this.world.position.y += e.clientY - this.dragging.y;
      this.dragging = { x: e.clientX, y: e.clientY };
    });
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const before = this.world.toLocal({ x: sx, y: sy });
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.world.scale.x * Math.exp(-e.deltaY * 0.0015)));
      this.world.scale.set(zoom);
      const after = this.world.toGlobal(before);
      this.world.position.x += sx - after.x;
      this.world.position.y += sy - after.y;
    }, { passive: false });
  }

  destroy(): void {
    this.app.destroy(true, { children: true });
  }
}
