// Game page entry: store + connection + 2D renderer, plus a one-line status bar.
// Input (WP15) and the full HUD (WP16) plug in here later.
import type { TFunction } from "i18next";

import { initI18n, pageLanguage } from "../i18n";
import { GameConnection } from "../net/connection";
import { PixiRenderer } from "../render2d/PixiRenderer";
import { msUntil } from "../sim/interp";
import { GameStore } from "../state/store";

interface PageConfig { game: string; wsPath: string; seat: number | null; lang: string }

function wsUrl(path: string): string {
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${path}`;
}

function statusText(t: TFunction, store: GameStore, now: number, link: string): string {
  const s = store.state;
  if (link !== "open") return t(link === "connecting" && !s ? "connecting" : "reconnecting");
  if (!s) return t("loading");
  const parts: string[] = [];
  if (store.seat === null) parts.push(t("status.spectator"));
  if (s.phase === "finished") {
    parts.push(t("status.finished"));
    const winner = s.winner === null ? undefined : store.player(s.winner);
    if (winner) parts.push(t("status.winner", { name: winner.name }));
  } else if (!s.clock_started) {
    parts.push(t("status.setup"));
  } else {
    parts.push(t("status.nextRoll", { seconds: Math.ceil(msUntil(s.next_roll_at, now) / 1000) }));
    if (s.last_roll) parts.push(t("status.lastRoll", { sum: s.last_roll.reduce((a, b) => a + b, 0) }));
  }
  return parts.join(" · ");
}

async function main(): Promise<void> {
  const root = document.getElementById("game-root");
  const configEl = document.getElementById("game-config");
  if (!root || !configEl) return;
  const config = JSON.parse(configEl.textContent ?? "{}") as PageConfig;
  const i18n = await initI18n(pageLanguage());
  const t = i18n.t.bind(i18n) as TFunction;

  root.innerHTML = "";
  const canvasHost = document.createElement("div");
  canvasHost.className = "game-canvas";
  const status = document.createElement("div");
  status.className = "game-status";
  status.setAttribute("role", "status");
  root.append(canvasHost, status);

  const store = new GameStore();
  let link = "connecting";
  const connection = new GameConnection({
    url: wsUrl(config.wsPath), lang: config.lang, store,
    onStatus: (s) => (link = s),
  });
  const renderer = new PixiRenderer();
  await renderer.mount(canvasHost);
  connection.start();
  window.addEventListener("resize", () => renderer.fit());

  let lastStatus = "";
  const frame = () => {
    const now = connection.clock.now();
    renderer.update(store, now);
    const text = statusText(t, store, now, link);
    if (text !== lastStatus) {
      status.textContent = text;
      lastStatus = text;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  // For debugging and end-to-end tests.
  (window as unknown as { island: object }).island = { store, connection, renderer };
}

void main();
