// PixiJS 2D renderer. World units are hex radii scaled by UNIT pixels; the camera
// is the transform of the world container, moved by the input package through
// panBy / zoomAt / centerOn.
import { Application, Container, Graphics, Sprite, Text, Texture } from "pixi.js";

import { BoardGeometry, hexCenter, hexCorners, type Pt } from "../board/geometry";
import type { BoardMsg, Resource } from "../protocol/types";
import type { Insets, Overlays, PickResult, Renderer } from "../render/Renderer";
import { constructionProgress, settlerPosition } from "../sim/interp";
import { ownGatherNumbers } from "../state/settlers";
import { agePlayer } from "../state/ages";
import { known, type GameStore } from "../state/store";
import { drawBuilding } from "./buildings";
import { drawTerrainDecor, drawWaves } from "./decor";
import { drawHarbor } from "./harbor";
import * as P from "./palette";

const UNIT = 60;
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 4;
const MAX_RESOLUTION = 2;
/** Largest side of the cached board texture, in pixels. Phones get a smaller one and no
 * multisampling: a 4096px multisampled texture takes about 256 MB, enough for some
 * phones to drop the WebGL context, which blanks the board. */
const MAX_CACHE_PX = 4096;
const MAX_CACHE_PX_PHONE = 3072;
/** Build candidates: dash and gap along a road (hex radii), line width (px), dashes round a spot. */
const DASH = 0.08;
const GAP = 0.075;
const CAND_W = 4;
const RING_DASHES = 8;
/** Roads stop this share of the edge short of each vertex. */
const ROAD_INSET = 0.18;
/** One beat of the chosen candidate's glow (ms). */
const PULSE_MS = 1100;
/** The chosen spot's preview building is see-through, so it never passes for a built one. */
const GHOST_ALPHA = 0.5;
/** Smallest width and height (hex radii) the camera frames at the start under Growing sight. */
const MIN_PARTIAL_SPAN = 8;
/** Rings of mist drawn round the land a player has seen (Growing sight), and how thick
 * each one is, from the edge of the seen land outwards: a soft fade, not a wall. */
const MIST_ALPHA = [0.55, 0.85, 1, 1];
const CLOUD_RINGS = MIST_ALPHA.length;
/** Diameter of one soft puff of mist, in hex radii: puffs overlap so no hex outline shows. */
const MIST_PUFF = 3.4;

/** Veil over land seen before but not in sight now: puff size (hex radii) and thickness.
 * Under Live fog what stands there is only remembered, so the veil is thicker. */
const VEIL_PUFF = 2.2;
const VEIL_ALPHA = 0.5;
const VEIL_ALPHA_SEEN = 0.42;
/** The line round the land in sight now (the field of vision). */
const SIGHT_LINE = { width: 3, color: 0xfff3c4, alpha: 0.85 };

let puffTexture: Texture | null = null;
/** A white disc that fades out towards its rim (drawn once, tinted per use). Soft
 * sprites instead of a blur filter: filters get clipped to the screen when the board
 * is cached, and are slow on phones. */
function puff(): Texture {
  if (puffTexture) return puffTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.4, "rgba(255,255,255,0.95)");
  grad.addColorStop(0.7, "rgba(255,255,255,0.6)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);
  puffTexture = Texture.from(canvas);
  return puffTexture;
}
const HEX_DIRS: [number, number][] = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];

/** A small deterministic hash of a hex position (0..1), so the mist looks the same every redraw. */
function hexNoise(q: number, r: number, salt: number): number {
  let h = (q * 374761393 + r * 668265263 + salt * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

/** Dashes from ``a`` to ``b`` (pixels), centred so both ends look the same. */
function dashedLine(g: Graphics, a: Pt, b: Pt, dash: number, gap: number): void {
  const len = Math.hypot(b.x - a.x, b.y - a.y);
  if (len <= 0) return;
  const n = Math.max(1, Math.round((len + gap) / (dash + gap)));
  const d = (len - gap * (n - 1)) / n;
  const ux = (b.x - a.x) / len;
  const uy = (b.y - a.y) / len;
  for (let i = 0; i < n; i++) {
    const s0 = i * (d + gap);
    g.moveTo(a.x + ux * s0, a.y + uy * s0).lineTo(a.x + ux * (s0 + d), a.y + uy * (s0 + d));
  }
}

/** True for colours that need a dark halo to show (white, yellow). */
function isLight(c: number): boolean {
  const r = (c >> 16) & 0xff;
  const g = (c >> 8) & 0xff;
  const b = c & 0xff;
  return r * 299 + g * 587 + b * 114 > 150_000;
}

/** A ring of ``n`` dashes round (x, y). */
function dashedRing(g: Graphics, x: number, y: number, r: number, n: number): void {
  const step = (Math.PI * 2) / n;
  for (let i = 0; i < n; i++) {
    const a0 = i * step;
    g.moveTo(x + Math.cos(a0) * r, y + Math.sin(a0) * r).arc(x, y, r, a0, a0 + step * 0.6);
  }
}

export class PixiRenderer implements Renderer {
  private app = new Application();
  private world = new Container();
  private boardLayer = new Container();
  private piecesLayer = new Graphics();
  private overlayLayer = new Graphics();
  private progressLayer = new Graphics();
  private settlerLayer = new Graphics();
  /** Gathering numbers under the viewer's own settlers (settlers variation), by settler id. */
  private settlerLabels = new Container();
  private settlerLabelText = new Map<number, Text>();
  private robberLayer = new Graphics();
  /** Under fog: a light veil over land seen before but not in sight now, and a line
   * round the land in sight. */
  private veilLayer = new Container();
  private veilKey = "";
  private focusLayer = new Graphics();
  private geo: BoardGeometry | null = null;
  private board: BoardMsg | null = null;
  private drawnVersion = -1;
  /** Resolution the static board is cached at (0 = not cached yet). */
  private cacheRes = 0;
  private overlays: Overlays = {};
  private store: GameStore | null = null;
  private lastNow = 0;
  private resizeObserver: ResizeObserver | null = null;
  private coarse = false;
  /** Set when the GPU lost what it held (context lost, page hidden): redraw the board. */
  private boardStale = false;
  private onContextRestored = () => { this.boardStale = true; };
  private onVisibility = () => { if (document.visibilityState === "visible") this.boardStale = true; };
  private fitInsets: () => Insets = () => ({ top: 0, right: 0, bottom: 0, left: 0 });

  async mount(el: HTMLElement): Promise<void> {
    // Phones: no MSAA and at most 2x pixels, which keeps the frame rate up and the battery cool.
    const coarse = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
    this.coarse = coarse;
    // The sea around the board is the page's own gradient behind a transparent canvas.
    await this.app.init({ resizeTo: el, backgroundAlpha: 0, antialias: !coarse, autoDensity: true,
                          resolution: Math.min(window.devicePixelRatio || 1, MAX_RESOLUTION),
                          ...(coarse ? { powerPreference: "low-power" as const } : {}) });
    el.appendChild(this.app.canvas);
    this.keepCentreOnResize(el);
    // Phones drop the WebGL context when the game goes to the background (or runs short of
    // memory). Pixi restores the context, but the cached board texture comes back empty and
    // the number tokens' text textures come back blank (their canvases went back to a shared
    // pool), so the board is drawn again from scratch.
    this.app.canvas.addEventListener("webglcontextrestored", this.onContextRestored);
    document.addEventListener("visibilitychange", this.onVisibility);
    this.world.addChild(this.boardLayer, this.piecesLayer, this.progressLayer, this.robberLayer, this.veilLayer,
                        this.overlayLayer, this.focusLayer, this.settlerLayer, this.settlerLabels);
    this.app.stage.addChild(this.world);
  }

  update(store: GameStore, now: number): void {
    this.store = store;
    this.lastNow = now;
    if (this.boardStale && this.board && this.geo) {
      this.boardStale = false;
      this.drawBoard();
      this.cacheRes = 0;
      this.drawnVersion = -1;
    }
    if (store.board && store.board !== this.board) {
      // Newly seen land (Growing sight) redraws the board but leaves the camera where it is.
      const refit = this.board === null || !store.board.partial;
      this.board = store.board;
      this.geo = new BoardGeometry(store.board);
      this.drawBoard();
      this.cacheRes = 0;
      if (refit) this.fit();
      this.drawnVersion = -1;
    }
    if (!this.geo || !store.state) return;
    if (store.version !== this.drawnVersion) {
      this.drawPieces(store);
      this.drawVeil(store);
      this.drawOverlays();
      this.drawnVersion = store.version;
    }
    this.drawMoving(store, now);
    this.drawFocus(now);
    this.cacheBoard();
  }

  // ------------------------------------------------------------------ board
  private drawBoard(): void {
    const geo = this.geo!;
    const board = this.board!;
    this.boardLayer.cacheAsTexture(false);
    this.boardLayer.removeChildren().forEach((c) => c.destroy({ children: true }));
    const fishing = new Map(board.fishing.map((f) => [f.hex, f.token]));
    const land = board.hexes.filter((h) => h.land && h.terrain);

    // Sea: a faint grid, darker fishing grounds and a few waves.
    const sea = new Graphics();
    for (const h of known(board.hexes)) {
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

    for (const h of known(board.hexes)) {
      const token = h.land ? h.token : fishing.get(h.id) ?? null;
      const hidden = token === null && (fishing.has(h.id) || (h.land && h.terrain !== null && h.terrain !== "desert"));
      if (token) this.boardLayer.addChild(this.token(geo.hex[h.id]!, token, !h.land));
      else if (hidden) this.boardLayer.addChild(this.hiddenToken(geo.hex[h.id]!));
    }
    if (board.partial) this.boardLayer.addChild(this.clouds(board));
    for (const hb of board.harbors) this.boardLayer.addChild(this.harbor(hb.vertices, hb.ratio, hb.resource));
  }

  /** Under fog: veil the land the player has seen but does not see now, and draw a line
   * round the land in sight, so the field of vision reads apart from what was seen
   * before (under Live fog what stands out of sight is only remembered). Redrawn only
   * when the sight changes. */
  private drawVeil(store: GameStore): void {
    const vis = store.state?.visibility;
    const board = store.board;
    const fog = !!board?.partial && !!vis && vis.map !== "open" && Array.isArray(vis.in_sight);
    const inSight = new Set(fog ? vis!.in_sight : []);
    const hexes = fog ? known(board!.hexes) : [];
    const out = hexes.filter((h) => !inSight.has(h.id));
    const inside = hexes.filter((h) => inSight.has(h.id));
    const key = `${vis?.map}|${out.map((h) => h.id).join(",")}|${inside.map((h) => h.id).join(",")}`;
    if (key === this.veilKey) return;
    this.veilKey = key;
    for (const c of this.veilLayer.removeChildren()) c.destroy();
    const alpha = vis?.map === "live_fog" ? VEIL_ALPHA : VEIL_ALPHA_SEEN;
    for (const h of out) {
      const c = hexCenter(h.q, h.r);
      const s = new Sprite(puff());
      s.anchor.set(0.5);
      s.width = s.height = VEIL_PUFF * UNIT;
      s.position.set(c.x * UNIT, c.y * UNIT);
      s.tint = P.CLOUD;
      s.alpha = alpha;
      this.veilLayer.addChild(s);
    }
    if (out.length && inside.length) this.veilLayer.addChild(this.sightLine(inside.map((h) => [h.q, h.r])));
  }

  /** A line along the outer edges of ``hexes`` (axial q, r): the edge of the field of vision. */
  private sightLine(hexes: [number, number][]): Graphics {
    const g = new Graphics();
    const keys = new Set(hexes.map(([q, r]) => `${q},${r}`));
    for (const [q, r] of hexes) {
      const corners = hexCorners(q, r);
      for (const [dq, dr] of HEX_DIRS) {
        if (keys.has(`${q + dq},${r + dr}`)) continue;
        // The shared side: the two corners one radius away from the neighbour's centre too.
        const n = hexCenter(q + dq, r + dr);
        const side = corners.filter((p) => Math.abs(Math.hypot(p.x - n.x, p.y - n.y) - 1) < 1e-6);
        if (side.length !== 2) continue;
        g.moveTo(side[0]!.x * UNIT, side[0]!.y * UNIT).lineTo(side[1]!.x * UNIT, side[1]!.y * UNIT);
      }
    }
    return g.stroke({ ...SIGHT_LINE, cap: "round" });
  }

  /** Whether both ends of ``edge`` are on the board this player knows. */
  private knownEdge(edge: number): boolean {
    const e = this.board?.edges[edge];
    return !!e && !!this.geo?.vertex[e.v[0]] && !!this.geo?.vertex[e.v[1]];
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

  /** A token whose number is hidden until a building stands next to its hex. */
  private hiddenToken(c: Pt): Container {
    const box = new Container();
    box.position.set(c.x * UNIT, c.y * UNIT);
    const g = new Graphics()
      .circle(0, 0, UNIT * 0.26).fill({ color: P.TOKEN_BG, alpha: 0.55 })
      .stroke({ width: 1.5, color: P.TOKEN_RING, alpha: 0.6 });
    const label = new Text({ text: "?", style: { fontFamily: "Georgia, 'Times New Roman', serif", fontSize: UNIT * 0.26,
      fontWeight: "700", fill: P.TOKEN_TEXT } });
    label.anchor.set(0.5, 0.55);
    label.alpha = 0.7;
    box.addChild(g, label);
    return box;
  }

  /** Mist over the hexes round the seen land: thin at the coast of what the player
   * knows and thicker further out, blurred so it reads as weather, not as tiles. A few
   * brighter wisps drift over it. */
  private clouds(board: BoardMsg): Container {
    const seen = new Set(known(board.hexes).map((h) => `${h.q},${h.r}`));
    const ring = new Map<string, [number, number, number]>();
    let frontier = known(board.hexes).map((h) => [h.q, h.r] as [number, number]);
    for (let depth = 1; depth <= CLOUD_RINGS; depth++) {
      const next: [number, number][] = [];
      for (const [q, r] of frontier) {
        for (const [dq, dr] of HEX_DIRS) {
          const key = `${q + dq},${r + dr}`;
          if (seen.has(key) || ring.has(key)) continue;
          ring.set(key, [q + dq, r + dr, depth]);
          next.push([q + dq, r + dr]);
        }
      }
      frontier = next;
    }
    const box = new Container();
    const wisps: Sprite[] = [];
    for (const [q, r, depth] of ring.values()) {
      const c = hexCenter(q, r);
      const s = new Sprite(puff());
      s.anchor.set(0.5);
      s.width = s.height = MIST_PUFF * UNIT;
      // A little jitter so the edge of the mist is not a perfect honeycomb.
      s.position.set((c.x + (hexNoise(q, r, 5) - 0.5) * 0.3) * UNIT, (c.y + (hexNoise(q, r, 6) - 0.5) * 0.3) * UNIT);
      s.tint = P.CLOUD;
      s.alpha = MIST_ALPHA[depth - 1]!;
      box.addChild(s);
      if (depth > 1 && hexNoise(q, r, 1) < 0.4) {
        // A brighter, elongated wisp drifting over the mist.
        const w = new Sprite(puff());
        w.anchor.set(0.5);
        w.width = (1.1 + hexNoise(q, r, 4) * 0.9) * UNIT;
        w.height = w.width * 0.38;
        w.position.set((c.x + (hexNoise(q, r, 2) - 0.5) * 0.8) * UNIT, (c.y + (hexNoise(q, r, 3) - 0.5) * 0.6) * UNIT);
        w.tint = P.CLOUD_LIGHT;
        w.alpha = 0.6;
        wisps.push(w);
      }
    }
    for (const w of wisps) box.addChild(w);
    return box;
  }

  private harbor(vertices: number[], ratio: number, resource: Resource | null): Container {
    const geo = this.geo!;
    const a = geo.vertex[vertices[0]!]!;
    const b = geo.vertex[vertices[1]!]!;
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    // Push the medallion out to sea: away from the centre of the land hexes next to the edge.
    const out = this.seaward(mid);
    const pos = { x: mid.x + out.x * 0.55, y: mid.y + out.y * 0.55 };
    const px = (p: Pt) => ({ x: p.x * UNIT, y: p.y * UNIT });
    return drawHarbor(px(a), px(b), px(pos), ratio, resource, UNIT);
  }

  private seaward(p: Pt): Pt {
    const geo = this.geo!;
    let sx = 0;
    let sy = 0;
    for (const h of known(this.board!.hexes)) {
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
    const res = Math.min(step, this.maxCachePx() / side);
    if (Math.abs(res - this.cacheRes) < 1e-6) return;
    this.cacheRes = res;
    this.boardLayer.cacheAsTexture(false);
    this.boardLayer.cacheAsTexture({ resolution: res, antialias: !this.coarse });
  }

  /** The cache limit for this device, never above what its GPU can hold in one texture. */
  private maxCachePx(): number {
    const limit = this.coarse ? MAX_CACHE_PX_PHONE : MAX_CACHE_PX;
    const gl = (this.app.renderer as { gl?: WebGLRenderingContext }).gl;
    const gpu = gl && !gl.isContextLost() ? Number(gl.getParameter(gl.MAX_TEXTURE_SIZE)) : 0;
    return gpu > 0 ? Math.min(limit, gpu) : limit;
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
    for (const b of s.buildings) {
      const p = geo.vertex[b.vertex];
      if (p) this.building(g, p, b.kind, P.playerColour(store.colourOf(b.seat)), 1, agePlayer(s, b.seat).age);
    }
    for (const c of s.constructions) {
      const p = geo.vertex[c.target];
      if (c.kind !== "road" && p) this.building(g, p, c.kind, P.playerColour(store.colourOf(c.seat)), 0.35);
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
    if (!this.knownEdge(edge)) return;
    const [a, b] = this.geo!.edgeEnds(edge);
    const t = ROAD_INSET;
    const a2 = { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    const b2 = { x: b.x + (a.x - b.x) * t, y: b.y + (a.y - b.y) * t };
    const line = (dx: number, dy: number) => g.moveTo(a2.x * UNIT + dx, a2.y * UNIT + dy).lineTo(b2.x * UNIT + dx, b2.y * UNIT + dy);
    line(1.5, 2.5).stroke({ width: 10, color: P.SHADOW, alpha: 0.3 * alpha, cap: "round" });
    line(0, 0).stroke({ width: 10, color: P.OUTLINE, alpha, cap: "round" });
    line(0, 0).stroke({ width: 7, color: colour, alpha, cap: "round" });
    line(0, -1.5).stroke({ width: 2, color: 0xffffff, alpha: 0.3 * alpha, cap: "round" });
  }

  private building(g: Graphics, p: Pt, kind: string, colour: number, alpha: number, age = 1): void {
    drawBuilding(g, kind, p.x * UNIT, p.y * UNIT, UNIT, colour, alpha, age);
  }

  /** Build mode candidates: dashed roads and dashed rings in the player's colour, all
   * the same width, over a dark outline so they show on every terrain. */
  private drawOverlays(): void {
    const geo = this.geo!;
    const g = this.overlayLayer.clear();
    const colour = P.playerColour(this.overlays.colour ?? "");
    // A pale halo keeps candidates apart from built roads (which have a dark outline);
    // light player colours get a dark one instead so they still show.
    const halo = isLight(colour) ? P.OUTLINE : 0xffffff;
    for (const e of this.overlays.edges ?? []) {
      if (e === this.overlays.focusEdge || !this.knownEdge(e)) continue;
      const [a, b] = this.roadEnds(e);
      dashedLine(g, a, b, UNIT * DASH, UNIT * GAP);
    }
    g.stroke({ width: CAND_W + 4, color: halo, alpha: 0.85, cap: "round" });
    for (const e of this.overlays.edges ?? []) {
      if (e === this.overlays.focusEdge || !this.knownEdge(e)) continue;
      const [a, b] = this.roadEnds(e);
      dashedLine(g, a, b, UNIT * DASH, UNIT * GAP);
    }
    g.stroke({ width: CAND_W, color: colour, cap: "round" });
    for (const v of this.overlays.vertices ?? []) {
      if (v === this.overlays.focusVertex) continue;
      const p = geo.vertex[v];
      if (!p) continue;
      g.circle(p.x * UNIT, p.y * UNIT, UNIT * 0.13).fill({ color: 0xffffff, alpha: 0.3 });
      dashedRing(g, p.x * UNIT, p.y * UNIT, UNIT * 0.13, RING_DASHES);
      g.stroke({ width: CAND_W + 4, color: halo, alpha: 0.85, cap: "round" });
      dashedRing(g, p.x * UNIT, p.y * UNIT, UNIT * 0.13, RING_DASHES);
      g.stroke({ width: CAND_W, color: colour, cap: "round" });
    }
    for (const h of this.overlays.hexes ?? []) {
      if (h === this.overlays.focusHex) continue;
      const p = geo.hex[h];
      if (!p) continue;
      dashedRing(g, p.x * UNIT, p.y * UNIT, UNIT * 0.42, 14);
      g.stroke({ width: CAND_W + 4, color: halo, alpha: 0.85, cap: "round" });
      dashedRing(g, p.x * UNIT, p.y * UNIT, UNIT * 0.42, 14);
      g.stroke({ width: CAND_W, color: P.HIGHLIGHT, cap: "round" });
    }
  }

  /** A road's drawn ends: the edge pulled in a little at both vertices. */
  private roadEnds(edge: number): [Pt, Pt] {
    const [a, b] = this.geo!.edgeEnds(edge);
    const t = ROAD_INSET;
    return [
      { x: (a.x + (b.x - a.x) * t) * UNIT, y: (a.y + (b.y - a.y) * t) * UNIT },
      { x: (b.x + (a.x - b.x) * t) * UNIT, y: (b.y + (a.y - b.y) * t) * UNIT },
    ];
  }

  /** The candidate about to be chosen: a pulsing glow and a see-through preview of the
   * piece itself (redrawn every frame, it is only a few shapes). */
  private drawFocus(now: number): void {
    const geo = this.geo!;
    const g = this.focusLayer.clear();
    const o = this.overlays;
    const colour = P.playerColour(o.colour ?? "");
    const pulse = 0.5 + 0.5 * Math.sin((now % PULSE_MS) / PULSE_MS * Math.PI * 2);
    const fe = o.focusEdge;
    if (fe != null && geo.edgeMid[fe]) {
      // Still dashed and see-through: a choice, not a built road (those are solid).
      const [a, b] = this.roadEnds(fe);
      g.moveTo(a.x, a.y).lineTo(b.x, b.y)
        .stroke({ width: 20 + 6 * pulse, color: P.HIGHLIGHT, alpha: 0.25 + 0.3 * pulse, cap: "round" });
      const halo = isLight(colour) ? P.OUTLINE : 0xffffff;
      dashedLine(g, a, b, UNIT * DASH * 1.4, UNIT * GAP);
      g.stroke({ width: CAND_W + 7, color: halo, alpha: 0.9, cap: "round" });
      dashedLine(g, a, b, UNIT * DASH * 1.4, UNIT * GAP);
      g.stroke({ width: CAND_W + 3, color: colour, alpha: 0.85, cap: "round" });
    }
    const fv = o.focusVertex;
    const fp = fv == null ? undefined : geo.vertex[fv];
    if (fp) {
      const x = fp.x * UNIT;
      const y = fp.y * UNIT;
      const r = UNIT * (0.24 + 0.05 * pulse);
      g.circle(x, y, r).fill({ color: P.HIGHLIGHT, alpha: 0.2 + 0.2 * pulse }).stroke({ width: 7, color: P.OUTLINE, alpha: 0.6 });
      g.circle(x, y, r).stroke({ width: 4, color: P.HIGHLIGHT });
      drawBuilding(g, o.focusKind ?? "settlement", x, y, UNIT, colour, GHOST_ALPHA);
    }
    const fh = o.focusHex;
    const hp = fh == null ? undefined : geo.hex[fh];
    if (hp) {
      const r = UNIT * (0.46 + 0.05 * pulse);
      g.circle(hp.x * UNIT, hp.y * UNIT, r).fill({ color: P.HIGHLIGHT, alpha: 0.18 + 0.15 * pulse })
        .stroke({ width: 8, color: P.OUTLINE, alpha: 0.6 });
      g.circle(hp.x * UNIT, hp.y * UNIT, r).stroke({ width: 5, color: P.HIGHLIGHT });
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
    const numbers = ownGatherNumbers(store.settings, s, store.seat);
    const labelled = new Set<number>();
    for (const settler of s.settlers) {
      const p = settlerPosition(geo, settler, now);
      if (!p) continue;

      const colour = P.playerColour(store.colourOf(settler.seat));
      const selected = this.overlays.selectedSettlers?.includes(settler.id) ?? false;
      const x = p.x * UNIT;
      const y = p.y * UNIT;
      if (selected) {
        // A pulsing gold ring and a little marker above: easy to spot among other tokens.
        const pulse = 0.5 + 0.5 * Math.sin((now % PULSE_MS) / PULSE_MS * Math.PI * 2);
        const r = UNIT * (0.25 + 0.03 * pulse);
        g.circle(x, y, r).fill({ color: P.HIGHLIGHT, alpha: 0.2 + 0.15 * pulse }).stroke({ width: 6, color: P.OUTLINE, alpha: 0.5 });
        g.circle(x, y, r).stroke({ width: 3, color: P.HIGHLIGHT });
        const my = y - UNIT * (0.36 + 0.04 * pulse);
        g.poly([x - UNIT * 0.08, my - UNIT * 0.07, x + UNIT * 0.08, my - UNIT * 0.07, x, my + UNIT * 0.03])
          .fill(P.HIGHLIGHT).stroke({ width: 2, color: P.OUTLINE, join: "round" });
      }
      g.ellipse(x + 2, y + UNIT * 0.14, UNIT * 0.15, UNIT * 0.05).fill({ color: P.SHADOW, alpha: 0.4 });
      g.circle(x, y, UNIT * 0.16).fill(colour).stroke({ width: selected ? 4 : 2, color: selected ? P.HIGHLIGHT : P.OUTLINE });
      g.circle(x - UNIT * 0.05, y - UNIT * 0.06, UNIT * 0.05).fill({ color: 0xffffff, alpha: 0.35 });
      // A tiny figure on the token: head and shoulders.
      g.circle(x, y - UNIT * 0.05, UNIT * 0.045).fill(P.OUTLINE);
      g.ellipse(x, y + UNIT * 0.05, UNIT * 0.075, UNIT * 0.045).fill(P.OUTLINE);
      if (settler.path.length) {
        let prev = settler.step ? geo.vertex[settler.step.to_v] ?? p : p;
        for (const v of settler.path) {
          const q = geo.vertex[v];
          if (!q) break;
          g.moveTo(prev.x * UNIT, prev.y * UNIT).lineTo(q.x * UNIT, q.y * UNIT);
          prev = q;
        }
        g.stroke({ width: 2, color: colour, alpha: 0.7 });
      }
      const nums = numbers.get(settler.id);
      if (nums) {
        labelled.add(settler.id);
        this.gatherLabel(g, settler.id, nums, x, y);
      }
    }
    for (const [id, text] of this.settlerLabelText) {
      if (labelled.has(id)) continue;
      text.destroy();
      this.settlerLabelText.delete(id);
    }
  }

  /** A small pill under a settler with the numbers it gathers on (e.g. "2·12"). */
  private gatherLabel(g: Graphics, id: number, nums: number[], x: number, y: number): void {
    const value = nums.join("·");
    let text = this.settlerLabelText.get(id);
    if (!text || text.text !== value) {
      text?.destroy();
      text = new Text({ text: value, style: { fontFamily: "Georgia, 'Times New Roman', serif", fontSize: UNIT * 0.2,
                                             fontWeight: "bold", fill: P.OUTLINE } });
      text.anchor.set(0.5);
      this.settlerLabels.addChild(text);
      this.settlerLabelText.set(id, text);
    }
    const ly = y + UNIT * 0.4;
    const w = Math.max(UNIT * 0.24, text.width + UNIT * 0.1);
    g.roundRect(x - w / 2, ly - UNIT * 0.11, w, UNIT * 0.22, UNIT * 0.11).fill({ color: 0xfff6dc, alpha: 0.92 })
      .stroke({ width: 1.5, color: P.OUTLINE });
    text.position.set(x, ly);
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
    const box = { minX: Math.min(...xs) - 1, minY: Math.min(...ys) - 1, maxX: Math.max(...xs) + 1, maxY: Math.max(...ys) + 1 };
    // Growing sight starts with a few hexes: frame some cloud round them rather than zooming right in.
    if (this.board!.partial) {
      const grow = (lo: number, hi: number): [number, number] => {
        const pad = Math.max(0, MIN_PARTIAL_SPAN - (hi - lo)) / 2;
        return [lo - pad, hi + pad];
      };
      [box.minX, box.maxX] = grow(box.minX, box.maxX);
      [box.minY, box.maxY] = grow(box.minY, box.maxY);
    }
    return box;
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
      if (!p) continue;
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
    this.app.canvas.removeEventListener("webglcontextrestored", this.onContextRestored);
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.app.destroy(true, { children: true });
  }
}
