// Keyboard and mouse controls: turns key presses and pointer gestures into
// intents (move_settler, build) and camera moves. It reads the store, never
// changes it, and only knows the renderer through the Renderer interface.
import { BoardGeometry, dist2, walkableNeighbours, type Pt } from "../board/geometry";
import type { BuildKind, Intent, SettlerView } from "../protocol/types";
import type { Overlays, Renderer } from "../render/Renderer";
import { settlerPosition } from "../sim/interp";
import type { GameStore } from "../state/store";
import { type Action, type Bindings, comboOf, keymap } from "./bindings";
import { heldDirection, neighbourToward } from "./directions";

export type BuildChoice = "road" | "settlement" | "city";

export interface ModeInfo { kind: BuildChoice; count: number }

export interface MenuItem { label: BuildChoice | "walk"; run: () => void }

export interface InputOptions {
  store: GameStore;
  renderer: Renderer;
  send: (intent: Intent) => string | null;
  /** Estimated server time (ms). */
  now: () => number;
  bindings: Bindings;
  /** Build mode changed (null = left build mode). */
  onMode?: (mode: ModeInfo | null) => void;
  /** Actions the HUD owns (open_trade, buy_dev_card). */
  onAction?: (action: Action) => void;
  /** Show a right-click menu at a screen point; returns a close function. */
  showMenu?: (x: number, y: number, items: MenuItem[]) => () => void;
}

/** Tunables for feel; client-side only, they never affect game rules. */
export const FEEL = {
  /** Queue the next keyboard step when the current one has this share left (or less). */
  queueShare: 0.35,
  /** ...or this many ms left, whichever is larger (covers network latency). */
  queueMs: 300,
  /** Forget an unconfirmed move after this long and allow a new one. */
  awaitMs: 1500,
  dragPx: 6,
  cameraKeyPxPerS: 700,
  edgePushPx: 12,
  edgePushPxPerS: 600,
  zoomStep: 1.2,
  wheelZoom: 0.0015,
} as const;

const DIRS: ReadonlySet<Action> = new Set(["move_up", "move_down", "move_left", "move_right"]);
const CAMERA: Partial<Record<Action, Pt>> = {
  camera_up: { x: 0, y: 1 }, camera_down: { x: 0, y: -1 }, camera_left: { x: 1, y: 0 }, camera_right: { x: -1, y: 0 },
};
const BUILD_KEYS: Partial<Record<Action, BuildChoice>> = {
  build_road: "road", build_settlement: "settlement", build_city: "city",
};
const BUILDABLE_FIELD = { road: "roads", settlement: "settlements", city: "cities" } as const;

interface Awaiting { target: number; at: number }
interface PendingBuild { kind: BuildChoice; target: number; spots: number[] }

export class InputController {
  selected: number[] = [];
  /** True while a HUD dialog is open: keys go to the dialog, not the game. */
  paused = false;
  mode: { kind: BuildChoice; focus: number | null } | null = null;
  private keys: Map<string, Action>;
  private held = new Set<Action>();
  private lean = new Map<number, number>();
  private awaiting = new Map<number, Awaiting>();
  private pending = new Map<number, PendingBuild>();
  private geo: BoardGeometry | null = null;
  private overlayKey = "";
  private modeCount = -1;
  private pointer: { x: number; y: number; inside: boolean } = { x: 0, y: 0, inside: false };
  private press: { button: number; x: number; y: number; dragging: boolean } | null = null;
  private box: HTMLDivElement | null = null;
  private closeMenu: (() => void) | null = null;
  private el: HTMLElement | null = null;
  private cleanup: (() => void)[] = [];

  constructor(private opts: InputOptions) {
    this.keys = keymap(opts.bindings);
  }

  setPaused(paused: boolean): void {
    this.paused = paused;
    if (paused) this.held.clear();
  }

  setBindings(b: Bindings): void {
    this.keys = keymap(b);
  }

  // ------------------------------------------------------------------ wiring
  attach(el: HTMLElement, win: Window = window): void {
    this.el = el;
    const on = <K extends keyof HTMLElementEventMap>(t: EventTarget, type: K | string, fn: (e: never) => void,
                                                     o?: AddEventListenerOptions) => {
      t.addEventListener(type, fn as EventListener, o);
      this.cleanup.push(() => t.removeEventListener(type, fn as EventListener, o));
    };
    on(win, "keydown", (e: KeyboardEvent) => this.keyDown(e));
    on(win, "keyup", (e: KeyboardEvent) => this.keyUp(e));
    on(win, "blur", () => this.held.clear());
    on(el, "contextmenu", (e: MouseEvent) => e.preventDefault());
    on(el, "pointerdown", (e: PointerEvent) => this.pointerDown(e));
    on(win, "pointermove", (e: PointerEvent) => this.pointerMove(e));
    on(win, "pointerup", (e: PointerEvent) => this.pointerUp(e));
    on(el, "pointerleave", () => (this.pointer.inside = false));
    on(el, "dblclick", (e: MouseEvent) => this.doubleClick(e));
    on(el, "wheel", (e: WheelEvent) => {
      e.preventDefault();
      const p = this.local(e);
      this.opts.renderer.zoomAt(Math.exp(-e.deltaY * FEEL.wheelZoom), p.x, p.y);
    }, { passive: false });
  }

  detach(): void {
    this.cleanup.forEach((f) => f());
    this.cleanup = [];
  }

  // ------------------------------------------------------------------ helpers
  private get state() { return this.opts.store.state; }

  private geometry(): BoardGeometry | null {
    const board = this.opts.store.board;
    if (board && this.geo?.board !== board) this.geo = new BoardGeometry(board);
    return board ? this.geo : null;
  }

  private mine(): SettlerView[] {
    const s = this.state;
    const seat = this.opts.store.seat;
    if (!s || seat === null || s.phase === "finished") return [];
    return s.settlers.filter((x) => x.seat === seat).sort((a, b) => a.id - b.id);
  }

  private settler(id: number): SettlerView | undefined {
    return this.state?.settlers.find((s) => s.id === id);
  }

  private selectedSettlers(): SettlerView[] {
    const mine = this.mine();
    return this.selected.map((id) => mine.find((s) => s.id === id)).filter((s): s is SettlerView => !!s);
  }

  private settlerAt(s: SettlerView): Pt {
    return settlerPosition(this.geometry()!, s, this.opts.now());
  }

  private local(e: { clientX: number; clientY: number }): Pt {
    const r = this.el?.getBoundingClientRect();
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) };
  }

  private send(intent: Intent): void {
    this.opts.send(intent);
  }

  /** Where a settler's queued walk ends. */
  private frontier(s: SettlerView): number {
    return s.path.length ? s.path[s.path.length - 1]! : s.step ? s.step.to_v : s.vertex;
  }

  private atRest(s: SettlerView): boolean {
    return !s.step && s.path.length === 0;
  }

  private busy(id: number): boolean {
    return this.state?.constructions.some((c) => c.builder === id) ?? false;
  }

  // ------------------------------------------------------------------ selection
  select(ids: number[], add = false): void {
    const next = add ? [...new Set([...this.selected, ...ids])] : ids;
    this.selected = next;
  }

  private selectIndex(n: number): void {
    const s = this.mine()[n];
    if (s) this.select([s.id]);
  }

  private selectNext(): void {
    const mine = this.mine();
    if (!mine.length) return;
    const cur = mine.findIndex((s) => s.id === this.selected[0]);
    this.select([mine[(cur + 1) % mine.length]!.id]);
  }

  // ------------------------------------------------------------------ keyboard
  private keyDown(e: KeyboardEvent): void {
    if (this.paused) return;
    const t = e.target as HTMLElement | null;
    if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
    const action = this.keys.get(comboOf(e));
    if (!action) return;
    e.preventDefault();
    if (e.repeat && (DIRS.has(action) || action in CAMERA)) return;
    this.action(action);
  }

  private keyUp(e: KeyboardEvent): void {
    // Release by key code whatever modifiers are now down (Shift may be let go first).
    for (const [combo, action] of this.keys) {
      if (combo.split("+").pop() === e.code) this.held.delete(action);
    }
  }

  /** Run one action (also used by tests and the HUD). */
  action(a: Action): void {
    this.closeMenu?.();
    if (DIRS.has(a)) {
      this.held.add(a);
      if (this.mode) this.moveFocus(a);
      else this.walkKeys();
      return;
    }
    if (a in CAMERA) { this.held.add(a); return; }
    const kind = BUILD_KEYS[a];
    if (kind) { this.toggleMode(kind); return; }
    switch (a) {
      case "select_next": this.mode ? this.cycleFocus(1) : this.selectNext(); break;
      case "select_1": this.selectIndex(0); break;
      case "select_2": this.selectIndex(1); break;
      case "select_3": this.selectIndex(2); break;
      case "confirm": if (this.mode?.focus != null) this.build(this.mode.kind, this.mode.focus); break;
      case "cancel": this.setMode(null); break;
      case "zoom_in": case "zoom_out": {
        const r = this.el?.getBoundingClientRect();
        const f = a === "zoom_in" ? FEEL.zoomStep : 1 / FEEL.zoomStep;
        this.opts.renderer.zoomAt(f, (r?.width ?? 0) / 2, (r?.height ?? 0) / 2);
        break;
      }
      case "center_selected": this.centerSelected(); break;
      default: this.opts.onAction?.(a);
    }
  }

  private centerSelected(): void {
    const s = this.selectedSettlers()[0];
    if (s && this.geometry()) this.opts.renderer.centerOn(this.settlerAt(s));
  }

  /** Keyboard walking: queue one more step for each selected settler when it is due. */
  private walkKeys(): void {
    const dir = heldDirection(this.held);
    const geo = this.geometry();
    const board = this.opts.store.board;
    if (!dir || !geo || !board) return;
    const now = this.opts.now();
    for (const s of this.selectedSettlers()) {
      if (!this.stepDue(s, now)) continue;
      const from = this.frontier(s);
      const fromAt = this.opts.renderer.worldToScreen(geo.vertex[from]!);
      const ns = walkableNeighbours(board, from).map((id) => ({ id, at: this.opts.renderer.worldToScreen(geo.vertex[id]!) }));
      const pick = neighbourToward(fromAt, ns, dir, this.lean.get(s.id) ?? -1);
      if (!pick) continue;
      if (pick.side) this.lean.set(s.id, -pick.side);
      this.pending.delete(s.id);
      this.move(s.id, pick.id, "append");
    }
  }

  private stepDue(s: SettlerView, now: number): boolean {
    if (!this.confirmed(s) || s.path.length) return false;
    return !s.step || this.stepEnding(s, now);
  }

  private stepEnding(s: SettlerView, now: number): boolean {
    const st = s.step!;
    const left = st.t1 - now;
    return left <= Math.max(FEEL.queueMs, (st.t1 - st.t0) * FEEL.queueShare);
  }

  private move(settler: number, to: number, mode: "replace" | "append"): void {
    this.awaiting.set(settler, { target: to, at: this.opts.now() });
    this.send({ a: "move_settler", settler, to_vertex: to, mode });
  }

  /** Walk the selected settlers to a vertex (right-click). */
  walkTo(v: number, append = false): void {
    for (const s of this.selectedSettlers()) {
      this.pending.delete(s.id);
      this.move(s.id, v, append ? "append" : "replace");
    }
  }

  // ------------------------------------------------------------------ build mode
  private candidates(kind: BuildChoice): number[] {
    return this.state?.buildable?.[BUILDABLE_FIELD[kind]] ?? [];
  }

  private spotPos(kind: BuildChoice, id: number): Pt | undefined {
    const geo = this.geometry();
    return kind === "road" ? geo?.edgeMid[id] : geo?.vertex[id];
  }

  private reference(): Pt | null {
    const s = this.selectedSettlers()[0] ?? this.mine()[0];
    return s && this.geometry() ? this.settlerAt(s) : null;
  }

  private toggleMode(kind: BuildChoice): void {
    if (this.mode?.kind === kind) { this.setMode(null); return; }
    if (this.opts.store.seat === null || !this.state || this.state.phase === "finished") return;
    const focus = this.nearest(kind, this.candidates(kind));
    this.setMode({ kind, focus });
  }

  private setMode(mode: { kind: BuildChoice; focus: number | null } | null): void {
    this.mode = mode;
    this.modeCount = mode ? this.candidates(mode.kind).length : -1;
    this.opts.onMode?.(mode && { kind: mode.kind, count: this.modeCount });
  }

  /** Candidates change while build mode is open (a build finishes, resources arrive). */
  private refreshMode(): void {
    const mode = this.mode!;
    const cands = this.candidates(mode.kind);
    if (mode.focus === null || !cands.includes(mode.focus)) {
      this.mode = { kind: mode.kind, focus: this.nearest(mode.kind, cands) };
    }
    if (cands.length !== this.modeCount) {
      this.modeCount = cands.length;
      this.opts.onMode?.({ kind: mode.kind, count: cands.length });
    }
  }

  private nearest(kind: BuildChoice, cands: number[]): number | null {
    const ref = this.reference();
    if (!ref) return cands[0] ?? null;
    let focus: number | null = null;
    let best = Infinity;
    for (const c of cands) {
      const p = this.spotPos(kind, c);
      if (p && dist2(p, ref) < best) { best = dist2(p, ref); focus = c; }
    }
    return focus;
  }

  /** Tab in build mode: next candidate by distance from the selected settler. */
  private cycleFocus(step: number): void {
    if (!this.mode) return;
    const ref = this.reference();
    const kind = this.mode.kind;
    const cands = [...this.candidates(kind)];
    if (!cands.length) return;
    if (ref) cands.sort((a, b) => dist2(this.spotPos(kind, a)!, ref) - dist2(this.spotPos(kind, b)!, ref));
    const i = this.mode.focus === null ? -1 : cands.indexOf(this.mode.focus);
    this.mode = { kind, focus: cands[(i + step + cands.length) % cands.length]! };
  }

  /** Arrow keys in build mode: the nearest candidate in that screen direction. */
  private moveFocus(a: Action): void {
    const mode = this.mode!;
    const dir = heldDirection(new Set([a]))!;
    const from = mode.focus === null ? null : this.spotPos(mode.kind, mode.focus);
    if (!from) { this.cycleFocus(1); return; }
    const r = this.opts.renderer;
    const f = r.worldToScreen(from);
    let best: { id: number; score: number } | null = null;
    for (const c of this.candidates(mode.kind)) {
      if (c === mode.focus) continue;
      const p = r.worldToScreen(this.spotPos(mode.kind, c)!);
      const dx = p.x - f.x;
      const dy = p.y - f.y;
      const len = Math.hypot(dx, dy);
      const cos = (dx * dir.x + dy * dir.y) / len;
      if (!(cos > 0)) continue;
      const score = len * (2 - cos);
      if (!best || score < best.score) best = { id: c, score };
    }
    if (best) this.mode = { ...mode, focus: best.id };
  }

  /** Mirrors engine construction.builder_required: setup builds (this player's setup,
   * which can outlast the game-wide setup phase once the dice clock starts) or "always". */
  private builderRequired(): boolean {
    if (this.state?.phase === "setup") return true;
    const seat = this.opts.store.seat;
    const me = seat === null ? undefined : this.opts.store.player(seat);
    if (me && !me.setup.done) return true;
    const settlers = this.opts.store.settings["settlers"] as { builder_required?: string } | undefined;
    return settlers?.builder_required === "always";
  }

  /** Build ``kind`` at ``target``: build now if a settler stands there, else walk one there first. */
  build(kind: BuildChoice, target: number): void {
    this.setMode(null);
    const geo = this.geometry();
    const board = this.opts.store.board;
    if (!geo || !board) return;
    const where: Intent = kind === "road"
      ? { a: "build", kind, edge: target }
      : { a: "build", kind: kind as BuildKind, vertex: target };
    if (!this.builderRequired()) { this.send(where); return; }
    const spots = kind === "road" ? [...board.edges[target]!.v] : [target];
    const pool = this.selectedSettlers().filter((s) => !this.busy(s.id));
    const free = pool.length ? pool : this.mine().filter((s) => !this.busy(s.id));
    const ready = free.find((s) => this.atRest(s) && spots.includes(s.vertex));
    if (ready) {
      this.send({ ...where, settler: ready.id } as Intent);
      return;
    }
    let best: { s: SettlerView; spot: number; d: number } | null = null;
    for (const s of free) {
      const from = geo.vertex[this.frontier(s)]!;
      for (const spot of spots) {
        const d = dist2(from, geo.vertex[spot]!);
        if (!best || d < best.d) best = { s, spot, d };
      }
    }
    if (!best) return;
    this.select([best.s.id]);
    this.move(best.s.id, best.spot, "replace");
    this.pending.set(best.s.id, { kind, target, spots });
  }

  /** The server refused an intent: drop whatever was waiting on it. */
  rejected(intent: Intent | undefined): void {
    if (!intent) return;
    if (intent.a === "move_settler") {
      this.awaiting.delete(intent.settler);
      this.pending.delete(intent.settler);
    }
  }

  private runPendingBuilds(): void {
    for (const [id, p] of this.pending) {
      const s = this.settler(id);
      if (!s) { this.pending.delete(id); continue; }
      if (!this.confirmed(s)) continue;
      if (!this.atRest(s)) continue;
      this.pending.delete(id);
      if (!p.spots.includes(s.vertex)) continue;
      const intent: Intent = p.kind === "road"
        ? { a: "build", kind: "road", edge: p.target, settler: id }
        : { a: "build", kind: p.kind, vertex: p.target, settler: id };
      this.send(intent);
    }
  }

  /** True once the server has accepted (or forgotten) this settler's last move. */
  private confirmed(s: SettlerView): boolean {
    const aw = this.awaiting.get(s.id);
    if (!aw) return true;
    if (this.frontier(s) === aw.target || s.path.includes(aw.target) || this.opts.now() - aw.at >= FEEL.awaitMs) {
      this.awaiting.delete(s.id);
      return true;
    }
    return false;
  }

  // ------------------------------------------------------------------ pointer
  private pointerDown(e: PointerEvent): void {
    if (this.paused) return;
    this.closeMenu?.();
    const p = this.local(e);
    this.press = { button: e.button, x: p.x, y: p.y, dragging: false };
    if (e.button === 2) this.rightClick(p, e.shiftKey);
  }

  private pointerMove(e: PointerEvent): void {
    const p = this.local(e);
    const r = this.el?.getBoundingClientRect();
    this.pointer = { x: p.x, y: p.y, inside: !!r && p.x >= 0 && p.y >= 0 && p.x <= r.width && p.y <= r.height };
    const pr = this.press;
    if (!pr) return;
    if (!pr.dragging && Math.hypot(p.x - pr.x, p.y - pr.y) > FEEL.dragPx) pr.dragging = true;
    if (!pr.dragging) return;
    if (pr.button === 1) {
      this.opts.renderer.panBy(p.x - pr.x, p.y - pr.y);
      pr.x = p.x;
      pr.y = p.y;
    } else if (pr.button === 0) {
      this.drawBox(pr, p);
    }
  }

  private pointerUp(e: PointerEvent): void {
    const pr = this.press;
    this.press = null;
    if (!pr) return;
    const p = this.local(e);
    if (pr.button === 0 && pr.dragging) this.boxSelect(pr, p, e.shiftKey);
    else if (pr.button === 0) this.leftClick(p, e.shiftKey);
    this.box?.remove();
    this.box = null;
  }

  private leftClick(p: Pt, shift: boolean): void {
    const hit = this.opts.renderer.pick(p.x, p.y);
    if (this.mode && hit && (hit.kind === "vertex" || hit.kind === "edge")) {
      const want = this.mode.kind === "road" ? "edge" : "vertex";
      if (hit.kind === want && this.candidates(this.mode.kind).includes(hit.id)) {
        this.build(this.mode.kind, hit.id);
        return;
      }
    }
    if (hit?.kind === "settler" && this.mine().some((s) => s.id === hit.id)) {
      if (shift && this.selected.includes(hit.id)) this.selected = this.selected.filter((x) => x !== hit.id);
      else this.select([hit.id], shift);
    }
  }

  private doubleClick(e: MouseEvent): void {
    const p = this.local(e);
    const hit = this.opts.renderer.pick(p.x, p.y);
    if (hit?.kind === "settler" && this.selected.includes(hit.id)) this.centerSelected();
  }

  private rightClick(p: Pt, shift: boolean): void {
    const geo = this.geometry();
    if (!geo || !this.selectedSettlers().length && !this.mine().length) return;
    if (!this.selectedSettlers().length) this.select([this.mine()[0]!.id]);
    const hit = this.opts.renderer.pick(p.x, p.y);
    const world = this.opts.renderer.screenToWorld(p.x, p.y);
    const items: MenuItem[] = [];
    let walkTo: number | null = null;
    if (hit?.kind === "vertex") {
      walkTo = hit.id;
      for (const kind of ["settlement", "city"] as const) {
        if (this.candidates(kind).includes(hit.id)) items.push({ label: kind, run: () => this.build(kind, hit.id) });
      }
    } else if (hit?.kind === "edge") {
      const [a, b] = this.opts.store.board!.edges[hit.id]!.v;
      walkTo = dist2(geo.vertex[a]!, world) <= dist2(geo.vertex[b]!, world) ? a : b;
      if (this.candidates("road").includes(hit.id)) items.push({ label: "road", run: () => this.build("road", hit.id) });
    } else {
      walkTo = geo.nearestVertex(world, 1);
    }
    const land = walkTo !== null && this.opts.store.board!.vertices[walkTo]!.hexes
      .some((h) => this.opts.store.board!.hexes[h]?.land);
    if (!land) walkTo = null;
    if (!items.length || !this.opts.showMenu) {
      if (walkTo !== null) this.walkTo(walkTo, shift);
      return;
    }
    const target = walkTo;
    if (target !== null) items.unshift({ label: "walk", run: () => this.walkTo(target, shift) });
    this.closeMenu = this.opts.showMenu(p.x, p.y, items.map((it) => ({
      label: it.label, run: () => { this.closeMenu = null; it.run(); },
    })));
    const close = this.closeMenu;
    this.closeMenu = () => { close(); this.closeMenu = null; };
  }

  private drawBox(a: Pt, b: Pt): void {
    if (!this.el) return;
    if (!this.box) {
      this.box = document.createElement("div");
      this.box.className = "select-box";
      this.el.appendChild(this.box);
    }
    Object.assign(this.box.style, {
      left: `${Math.min(a.x, b.x)}px`, top: `${Math.min(a.y, b.y)}px`,
      width: `${Math.abs(a.x - b.x)}px`, height: `${Math.abs(a.y - b.y)}px`,
    });
  }

  private boxSelect(a: Pt, b: Pt, add: boolean): void {
    if (!this.geometry()) return;
    const [x0, x1] = [Math.min(a.x, b.x), Math.max(a.x, b.x)];
    const [y0, y1] = [Math.min(a.y, b.y), Math.max(a.y, b.y)];
    const inside = this.mine().filter((s) => {
      const p = this.opts.renderer.worldToScreen(this.settlerAt(s));
      return p.x >= x0 && p.x <= x1 && p.y >= y0 && p.y <= y1;
    });
    if (inside.length) this.select(inside.map((s) => s.id), add);
  }

  // ------------------------------------------------------------------ per frame
  /** Call once per animation frame with the real elapsed time. */
  tick(dtMs: number): void {
    const mine = this.mine();
    this.selected = this.selected.filter((id) => mine.some((s) => s.id === id));
    if (!this.selected.length && mine.length) this.selected = [mine[0]!.id];
    if (this.mode) this.refreshMode();
    this.cameraKeys(dtMs);
    this.edgePush(dtMs);
    if (!this.mode) this.walkKeys();
    this.runPendingBuilds();
    this.pushOverlays();
  }

  private cameraKeys(dtMs: number): void {
    let x = 0;
    let y = 0;
    for (const a of this.held) {
      const d = CAMERA[a];
      if (d) { x += d.x; y += d.y; }
    }
    if (x || y) {
      const k = (FEEL.cameraKeyPxPerS * dtMs) / 1000;
      this.opts.renderer.panBy(x * k, y * k);
    }
  }

  private edgePush(dtMs: number): void {
    if (!this.pointer.inside || this.press || !this.el) return;
    const r = this.el.getBoundingClientRect();
    const { x, y } = this.pointer;
    const e = FEEL.edgePushPx;
    const dx = x < e ? 1 : x > r.width - e ? -1 : 0;
    const dy = y < e ? 1 : y > r.height - e ? -1 : 0;
    if (dx || dy) {
      const k = (FEEL.edgePushPxPerS * dtMs) / 1000;
      this.opts.renderer.panBy(dx * k, dy * k);
    }
  }

  private pushOverlays(): void {
    const o: Overlays = { selectedSettlers: this.selected };
    if (this.mode) {
      const cands = this.candidates(this.mode.kind);
      if (this.mode.kind === "road") { o.edges = cands; o.focusEdge = this.mode.focus; }
      else { o.vertices = cands; o.focusVertex = this.mode.focus; }
    }
    const key = JSON.stringify(o);
    if (key !== this.overlayKey) {
      this.overlayKey = key;
      this.opts.renderer.setOverlays(o);
    }
  }
}
