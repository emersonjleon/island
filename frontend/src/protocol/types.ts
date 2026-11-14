// Wire protocol (proto 1). Shapes follow docs/STAGE1_PLAN.md §4.3 and the golden
// fixtures in protocol/fixtures, which src/state/store.test.ts feeds through the store.

export const PROTO = 1;

export type Resource = "lumber" | "brick" | "wool" | "grain" | "ore" | "fish";
export type ResMap = Partial<Record<Resource, number>>;
export type BuildKind = "road" | "settlement" | "city" | "megacity";
export type Terrain = "forest" | "pasture" | "fields" | "hills" | "mountains" | "desert";

export interface HexInfo { id: number; q: number; r: number; land: boolean; terrain: Terrain | null; token: number | null }
export interface VertexInfo { id: number; q: number; r: number; c: "N" | "S"; hexes: number[]; adj_v: number[]; adj_e: number[] }
export interface EdgeInfo { id: number; v: [number, number]; hexes: number[] }
export interface HarborInfo { edge: number; vertices: number[]; resource: Resource | null; ratio: number }

export interface BoardMsg {
  t: "board";
  hexes: HexInfo[];
  vertices: VertexInfo[];
  edges: EdgeInfo[];
  fishing: { hex: number; token: number }[];
  harbors: HarborInfo[];
  robber_start: number | null;
}

export interface SettlerStep { edge: number; from_v: number; to_v: number; t0: number; t1: number }
export interface SettlerView { id: number; seat: number; vertex: number; path: number[]; step: SettlerStep | null }
export interface ConstructionView {
  id: number; seat: number; kind: BuildKind; target: number; builder: number | null; t0: number; t1: number; paid: ResMap; setup?: boolean;
}
export interface PlayerView {
  seat: number; name: string; colour: string;
  pieces: Partial<Record<BuildKind, number>>;
  setup: { remaining: Partial<Record<BuildKind, number>>; done: boolean; settlements_built: number };
  settlers: number[];
  hand?: ResMap; hand_count?: number; points?: number;
}
export interface BuildableSets { roads: number[]; settlements: number[]; cities: number[]; megacities?: number[] }

export interface GameStateView {
  phase: "setup" | "running" | "finished";
  now: number;
  viewer: number | null;
  bank: ResMap;
  players: PlayerView[];
  buildings: { kind: BuildKind; seat: number; vertex: number }[];
  roads: { edge: number; seat: number }[];
  settlers: SettlerView[];
  constructions: ConstructionView[];
  robber: number | null;
  clock_started: boolean;
  next_roll_at: number | null;
  last_roll: number[] | null;
  dice_history: number[];
  winner: number | null;
  finished_at: number | null;
  /** Stage 2. Lengths are keyed by seat (as a string). */
  longest_road?: { holder: number | null; lengths: Record<string, number> };
  buildable?: BuildableSets;
}

/** One engine event as the server sends it to this audience (already redacted). */
export type GameEvent = { k: string; at?: number; [field: string]: unknown };

export interface WelcomeMsg { t: "welcome"; game: string; seat: number | null; proto: number; settings: Record<string, unknown> }
export interface StateMsg { t: "state"; seq: number; now: number; state: GameStateView; resumed?: boolean }
export interface EventsMsg { t: "events"; seq: number; now: number; events: GameEvent[] }
export interface AckMsg { t: "ack"; cid: string }
export interface RejectMsg { t: "reject"; cid: string | null; code: string; params: Record<string, unknown> }
export interface NoticeMsg { t: "notice"; code: string; params: Record<string, unknown> }
export interface PongMsg { t: "pong"; c: number | null; now: number }

export type ServerMsg = WelcomeMsg | BoardMsg | StateMsg | EventsMsg | AckMsg | RejectMsg | NoticeMsg | PongMsg;

export type Intent =
  | { a: "move_settler"; settler: number; to_vertex: number; mode: "replace" | "append" }
  | { a: "build"; kind: BuildKind; vertex?: number; edge?: number; settler?: number }
  | { a: "cancel_build"; construction: number }
  | { a: "bank_trade"; give: ResMap; get: ResMap };

const KINDS = new Set(["welcome", "board", "state", "events", "ack", "reject", "notice", "pong"]);

export function parseServerMsg(data: string): ServerMsg | null {
  try {
    const msg = JSON.parse(data) as { t?: unknown };
    return typeof msg.t === "string" && KINDS.has(msg.t) ? (msg as ServerMsg) : null;
  } catch {
    return null;
  }
}
