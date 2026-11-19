// WebSocket client: reconnects with backoff, says hello, keeps the store in sync
// (asks for a full state when an events batch skips a seq), pings for clock sync
// and tracks intents by cid so the UI can show rejects. A socket that goes quiet
// (no frame for a few ping intervals: a network that vanished without closing it)
// is dropped and reopened, and the browser's online/offline events start or stop
// the retries at once.
import { PROTO, parseServerMsg, type ChatMsg, type PresenceMsg, type Intent, type RejectMsg, type ServerMsg } from "../protocol/types";
import { ServerClock } from "../sim/clock";
import type { GameStore } from "../state/store";

export interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: string }) => void) | null;
  onclose: ((ev: unknown) => void) | null;
}

export interface ConnectionOptions {
  url: string;
  lang: string;
  store: GameStore;
  clock?: ServerClock;
  socketFactory?: (url: string) => SocketLike;
  pingMs?: number;
  onReject?: (reject: RejectMsg, intent: Intent | undefined) => void;
  onNotice?: (code: string, params: Record<string, unknown>) => void;
  onStatus?: (status: LinkStatus, info: LinkInfo) => void;
  /** A frame counts as overdue after this long without one (default: three pings). */
  staleMs?: number;
  /** Where the online/offline events come from (default: window, when there is one). */
  events?: Pick<Window, "addEventListener" | "removeEventListener"> | null;
  /** Chat frames ride on the game socket but never touch the store. */
  onChat?: (msg: ChatMsg) => void;
}

export type LinkStatus = "connecting" | "open" | "closed";
/** ``attempt``: reconnection attempts since the link was last open (0 while it is);
 * ``retryAt``: Date.now() of the next attempt while closed, else null. */
export interface LinkInfo { attempt: number; retryAt: number | null }

/** Local code for an order given while the socket is down (translated like server codes). */
export const OFFLINE_CODE = "net.offline";

const OPEN = 1;
const MAX_BACKOFF_MS = 15000;
/** Chat lines written while the socket is (re)connecting wait for it, up to this many. */
const MAX_QUEUED_CHAT = 5;

export class GameConnection {
  readonly clock: ServerClock;
  private socket: SocketLike | null = null;
  private backoff = 500;
  private stopped = false;
  private nextCid = 1;
  private pending = new Map<string, Intent>();
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private chatQueue: string[] = [];
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private lastHeard = 0;
  private readonly onOnline = () => this.retryNow();
  private readonly onOffline = () => this.drop();

  constructor(private readonly opts: ConnectionOptions) {
    this.clock = opts.clock ?? new ServerClock();
  }

  start(): void {
    this.stopped = false;
    this.listen()?.addEventListener("online", this.onOnline);
    this.listen()?.addEventListener("offline", this.onOffline);
    this.open();
  }

  stop(): void {
    this.stopped = true;
    this.listen()?.removeEventListener("online", this.onOnline);
    this.listen()?.removeEventListener("offline", this.onOffline);
    if (this.pingTimer) clearInterval(this.pingTimer);
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.socket?.close();
  }

  get isOpen(): boolean {
    return this.socket !== null && this.socket.readyState === OPEN;
  }

  /** Try to reconnect now instead of waiting out the backoff (no-op while open or connecting). */
  retryNow(): void {
    if (this.stopped || this.retryTimer === null) return;
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.open();
  }

  /** Give up on the current socket (it went quiet, or the browser went offline) and retry. */
  drop(): void {
    const socket = this.socket;
    if (!socket || this.stopped) return;
    socket.onopen = socket.onmessage = socket.onclose = null;
    this.socket = null;
    try { socket.close(); } catch { /* already gone */ }
    this.closed();
  }

  /** Send an intent; returns its cid, or null when there is no connection (the order is
   * refused locally with ``net.offline`` rather than lost). */
  send(intent: Intent): string | null {
    if (!this.isOpen) {
      this.opts.onReject?.({ t: "reject", cid: null, code: OFFLINE_CODE, params: {} }, intent);
      return null;
    }
    const cid = `c${this.nextCid++}`;
    this.pending.set(cid, intent);
    this.raw({ t: "intent", cid, ...intent });
    return cid;
  }

  /** Send a chat line, or keep it until the socket (re)opens; false when too many are waiting. */
  say(text: string): boolean {
    if (this.socket && this.socket.readyState === OPEN) this.raw({ t: "chat", text });
    else if (this.chatQueue.length < MAX_QUEUED_CHAT) this.chatQueue.push(text);
    else return false;
    return true;
  }

  sync(): void {
    this.raw({ t: "sync", from_seq: this.opts.store.seq });
  }

  ping(): void {
    this.raw({ t: "ping", c: performance.now() });
  }

  /** Handle one frame from the server (public for tests). */
  handle(data: string): void {
    this.lastHeard = Date.now();
    const msg = parseServerMsg(data);
    if (!msg) return;
    this.observeTime(msg);
    switch (msg.t) {
      case "pong":
        if (typeof msg.c === "number") this.clock.sample(msg.c, msg.now);
        return;
      case "ack":
        this.pending.delete(msg.cid);
        return;
      case "reject": {
        const intent = msg.cid ? this.pending.get(msg.cid) : undefined;
        if (msg.cid) this.pending.delete(msg.cid);
        this.opts.onReject?.(msg, intent);
        return;
      }
      case "notice":
        this.opts.onNotice?.(msg.code, msg.params);
        return;
      case "chat":
        this.opts.onChat?.(msg);
        return;
      case "presence":
        this.opts.store.setPresence((msg as PresenceMsg).seat, (msg as PresenceMsg).online);
        return;
      default:
        if (this.opts.store.apply(msg) === "gap") this.sync();
    }
  }

  private observeTime(msg: ServerMsg): void {
    if ((msg.t === "state" || msg.t === "events") && typeof msg.now === "number") this.clock.hint(msg.now);
  }

  private raw(obj: object): void {
    if (this.socket && this.socket.readyState === OPEN) this.socket.send(JSON.stringify(obj));
  }

  private listen(): Pick<Window, "addEventListener" | "removeEventListener"> | null {
    if (this.opts.events !== undefined) return this.opts.events;
    return typeof window === "undefined" ? null : window;
  }

  private status(status: LinkStatus): void {
    const retryAt = status === "closed" && this.retryTimer !== null ? Date.now() + this.backoffUsed : null;
    this.opts.onStatus?.(status, { attempt: this.attempt, retryAt });
  }

  private backoffUsed = 0;

  private open(): void {
    const factory = this.opts.socketFactory ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
    this.status("connecting");
    const socket = factory(this.opts.url);
    this.socket = socket;
    socket.onopen = () => {
      this.backoff = 500;
      this.attempt = 0;
      this.lastHeard = Date.now();
      this.status("open");
      this.raw({ t: "hello", proto: PROTO, lang: this.opts.lang });
      this.ping();
      for (const text of this.chatQueue.splice(0)) this.raw({ t: "chat", text });
      if (this.pingTimer) clearInterval(this.pingTimer);
      const every = this.opts.pingMs ?? 5000;
      this.pingTimer = setInterval(() => {
        // A finished game has nobody left to answer pings: silence is expected, not a lost link.
        if (this.opts.store.state?.phase === "finished") return;
        if (Date.now() - this.lastHeard > (this.opts.staleMs ?? every * 3)) this.drop();
        else this.ping();
      }, every);
    };
    socket.onmessage = (ev) => this.handle(ev.data);
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null;
      this.closed();
    };
  }

  /** The socket is gone: forget unanswered intents (the next state is the truth) and retry. */
  private closed(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
    this.pending.clear();
    if (this.stopped) {
      this.status("closed");
      return;
    }
    this.attempt += 1;
    this.backoffUsed = this.backoff;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => { this.retryTimer = null; this.open(); }, this.backoff);
    this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
    this.status("closed");
  }
}
