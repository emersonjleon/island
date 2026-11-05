// WebSocket client: reconnects with backoff, says hello, keeps the store in sync
// (asks for a full state when an events batch skips a seq), pings for clock sync
// and tracks intents by cid so the UI can show rejects.
import { PROTO, parseServerMsg, type Intent, type RejectMsg, type ServerMsg } from "../protocol/types";
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
  onStatus?: (status: "connecting" | "open" | "closed") => void;
}

const OPEN = 1;
const MAX_BACKOFF_MS = 15000;

export class GameConnection {
  readonly clock: ServerClock;
  private socket: SocketLike | null = null;
  private backoff = 500;
  private stopped = false;
  private nextCid = 1;
  private pending = new Map<string, Intent>();
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly opts: ConnectionOptions) {
    this.clock = opts.clock ?? new ServerClock();
  }

  start(): void {
    this.stopped = false;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.socket?.close();
  }

  /** Send an intent; returns its cid. */
  send(intent: Intent): string {
    const cid = `c${this.nextCid++}`;
    this.pending.set(cid, intent);
    this.raw({ t: "intent", cid, ...intent });
    return cid;
  }

  sync(): void {
    this.raw({ t: "sync", from_seq: this.opts.store.seq });
  }

  ping(): void {
    this.raw({ t: "ping", c: performance.now() });
  }

  /** Handle one frame from the server (public for tests). */
  handle(data: string): void {
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

  private open(): void {
    const factory = this.opts.socketFactory ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
    this.opts.onStatus?.("connecting");
    const socket = factory(this.opts.url);
    this.socket = socket;
    socket.onopen = () => {
      this.backoff = 500;
      this.opts.onStatus?.("open");
      this.raw({ t: "hello", proto: PROTO, lang: this.opts.lang });
      this.ping();
      if (this.pingTimer) clearInterval(this.pingTimer);
      this.pingTimer = setInterval(() => this.ping(), this.opts.pingMs ?? 5000);
    };
    socket.onmessage = (ev) => this.handle(ev.data);
    socket.onclose = () => {
      if (this.pingTimer) clearInterval(this.pingTimer);
      this.opts.onStatus?.("closed");
      if (this.stopped) return;
      setTimeout(() => this.open(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
    };
  }
}
