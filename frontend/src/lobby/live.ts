// Live lobby page: refetch the seats block when the server says it changed,
// and follow the redirect once the game is running.

export type LobbyMessage = { t: "changed" } | { t: "started"; url: string } | { t: "pong" };

export interface LobbyPage {
  refreshSeats(): Promise<void>;
  navigate(url: string): void;
}

export function parseMessage(data: string): LobbyMessage | null {
  try {
    const msg = JSON.parse(data) as { t?: unknown; url?: unknown };
    if (msg.t === "changed" || msg.t === "pong") return { t: msg.t };
    if (msg.t === "started" && typeof msg.url === "string" && msg.url.startsWith("/")) {
      return { t: "started", url: msg.url };
    }
  } catch {
    // ignore malformed frames
  }
  return null;
}

export async function handleMessage(page: LobbyPage, msg: LobbyMessage): Promise<void> {
  if (msg.t === "changed") await page.refreshSeats();
  else if (msg.t === "started") page.navigate(msg.url);
}

export function wsUrl(path: string, loc: Location = window.location): string {
  const scheme = loc.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${loc.host}${path}`;
}

const MAX_BACKOFF_MS = 15000;

/** Connect and keep reconnecting with exponential backoff. Refreshes on reconnect to catch missed changes. */
export function connectLobby(path: string, page: LobbyPage): () => void {
  let socket: WebSocket | null = null;
  let backoff = 500;
  let stopped = false;
  let everOpened = false;

  const open = () => {
    socket = new WebSocket(wsUrl(path));
    socket.onopen = () => {
      if (everOpened) void page.refreshSeats();
      everOpened = true;
      backoff = 500;
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
  return () => {
    stopped = true;
    socket?.close();
  };
}
