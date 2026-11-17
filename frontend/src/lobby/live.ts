// Live lobby page: refetch the seats block when the server says it changed,
// follow the redirect once the game is running, and carry the waiting-room chat.

import { parseChatFrame, type ChatFrame } from "../chat/model";

export type LobbyMessage =
  | { t: "changed" }
  | { t: "started"; url: string }
  | { t: "pong" }
  | ChatFrame
  | { t: "notice"; code: string; params: Record<string, unknown> };

export interface LobbyPage {
  refreshSeats(): Promise<void>;
  navigate(url: string): void;
  chat?(frame: ChatFrame): void;
  notice?(code: string, params: Record<string, unknown>): void;
}

export function parseMessage(data: string): LobbyMessage | null {
  try {
    const msg = JSON.parse(data) as { t?: unknown; url?: unknown; code?: unknown; params?: unknown };
    if (msg.t === "changed" || msg.t === "pong") return { t: msg.t };
    if (msg.t === "started" && typeof msg.url === "string" && msg.url.startsWith("/")) {
      return { t: "started", url: msg.url };
    }
    if (msg.t === "chat") return parseChatFrame(msg);
    if (msg.t === "notice" && typeof msg.code === "string") {
      const params = msg.params && typeof msg.params === "object" ? (msg.params as Record<string, unknown>) : {};
      return { t: "notice", code: msg.code, params };
    }
  } catch {
    // ignore malformed frames
  }
  return null;
}

export async function handleMessage(page: LobbyPage, msg: LobbyMessage): Promise<void> {
  if (msg.t === "changed") await page.refreshSeats();
  else if (msg.t === "started") page.navigate(msg.url);
  else if (msg.t === "chat") page.chat?.(msg);
  else if (msg.t === "notice") page.notice?.(msg.code, msg.params);
}

export function wsUrl(path: string, loc: Location = window.location): string {
  const scheme = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${loc.host}${path}`;
}

const MAX_BACKOFF_MS = 15000;
/** Frames sent while the socket is (re)connecting wait for it, up to this many. */
const MAX_QUEUED = 5;

export interface LobbyConnection {
  /** Send a frame, or keep it until the socket opens; false when too many are waiting. */
  send(msg: object): boolean;
  close(): void;
}

/** Connect and keep reconnecting with exponential backoff. Refreshes on reconnect to catch missed changes. */
export function connectLobby(path: string, page: LobbyPage): LobbyConnection {
  let socket: WebSocket | null = null;
  let backoff = 500;
  let stopped = false;
  let everOpened = false;
  const queued: string[] = [];

  const open = () => {
    socket = new WebSocket(wsUrl(path));
    socket.onopen = () => {
      if (everOpened) void page.refreshSeats();
      everOpened = true;
      backoff = 500;
      while (queued.length && socket?.readyState === WebSocket.OPEN) socket.send(queued.shift()!);
    };
    socket.onmessage = (ev: MessageEvent<string>) => {
      const msg = parseMessage(ev.data);
      if (msg) void handleMessage(page, msg);
    };
    socket.onclose = () => {
      if (stopped) return;
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    };
  };
  open();
  return {
    send(msg) {
      const frame = JSON.stringify(msg);
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(frame);
      else if (queued.length < MAX_QUEUED) queued.push(frame);
      else return false;
      return true;
    },
    close() {
      stopped = true;
      socket?.close();
    },
  };
}
