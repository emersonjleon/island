// Chat model shared by the waiting room and the game page: the lines received so
// far (deduplicated, in order), unread counting and the resource emoji that turn
// into resource icons. No DOM here, so it is tested on its own.
import type { Resource } from "../protocol/types";

/** One chat line as the server sends it (see chat/services.py ``to_wire``). */
export interface ChatLine {
  id: number;
  name: string;
  /** Player colour name ("" for someone who is only watching). */
  colour: string;
  seat: number | null;
  player: boolean;
  text: string;
  /** Epoch milliseconds. */
  at: number;
}

export interface ChatFrame { t: "chat"; msgs: ChatLine[]; history: boolean }

/** Resource emoji offered by the chat's quick buttons; shown as the game's resource icons. */
export const RES_EMOJI: Record<Resource, string> = {
  lumber: "🌲", brick: "🧱", wool: "🐑", grain: "🌾", ore: "⛰️", fish: "🐟",
};

const EMOJI_RES = new Map<string, Resource>(
  (Object.entries(RES_EMOJI) as [Resource, string][]).map(([r, e]) => [e.replace("️", ""), r]),
);
const EMOJI_RE = new RegExp(`(${[...EMOJI_RES.keys()].join("|")})️?`, "gu");

export type TextPart = string | { res: Resource };

/** Split a message into plain text and resource icons. */
export function splitResources(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const m of text.matchAll(EMOJI_RE)) {
    const at = m.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    parts.push({ res: EMOJI_RES.get(m[1]!)! });
    last = at + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function isLine(v: unknown): v is ChatLine {
  const o = v as Partial<ChatLine> | null;
  return !!o && typeof o.id === "number" && typeof o.name === "string" && typeof o.text === "string";
}

/** A ``chat`` frame from either page's socket, or null for anything else. */
export function parseChatFrame(msg: unknown): ChatFrame | null {
  const o = msg as { t?: unknown; msgs?: unknown; history?: unknown } | null;
  if (!o || o.t !== "chat" || !Array.isArray(o.msgs)) return null;
  return {
    t: "chat",
    history: o.history === true,
    msgs: o.msgs.filter(isLine).map((m) => ({
      ...m, colour: typeof m.colour === "string" ? m.colour : "", seat: typeof m.seat === "number" ? m.seat : null,
      player: m.player === true, at: typeof m.at === "number" ? m.at : 0,
    })),
  };
}

export type ChatListener = (log: ChatLog, fresh: ChatLine[]) => void;

/** The conversation as this page has seen it. */
export class ChatLog {
  lines: ChatLine[] = [];
  /** Lines from others since the panel was last open. */
  unread = 0;
  open = false;
  /** The last refusal from the server (a "chat.*" code), until the next line arrives. */
  error: { code: string; params: Record<string, unknown> } | null = null;
  private ids = new Set<number>();
  private sent: string[] = [];
  private listeners = new Set<ChatListener>();

  constructor(private readonly keep = 200) {}

  subscribe(fn: ChatListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Remember a line this page sent, so its echo is not counted as unread. */
  markSent(text: string): void {
    this.sent.push(text.trim().replace(/\s+/g, " "));
    if (this.sent.length > 10) this.sent.shift();
  }

  /** Add a frame's lines. History (sent on every (re)connect) never counts as unread. */
  receive(frame: ChatFrame): ChatLine[] {
    const fresh = frame.msgs.filter((m) => !this.ids.has(m.id));
    if (!fresh.length) return [];
    for (const m of fresh) this.ids.add(m.id);
    if (!frame.history) this.error = null;
    this.lines = [...this.lines, ...fresh].sort((a, b) => a.id - b.id).slice(-this.keep);
    const others = frame.history ? [] : fresh.filter((m) => !this.takeOwn(m.text));
    if (!this.open) this.unread += others.length;
    for (const fn of this.listeners) fn(this, others);
    return others;
  }

  refused(code: string, params: Record<string, unknown> = {}): void {
    this.error = { code, params };
    for (const fn of this.listeners) fn(this, []);
  }

  setOpen(open: boolean): void {
    this.open = open;
    if (open) this.unread = 0;
    for (const fn of this.listeners) fn(this, []);
  }

  private takeOwn(text: string): boolean {
    const i = this.sent.indexOf(text);
    if (i < 0) return false;
    this.sent.splice(i, 1);
    return true;
  }
}
