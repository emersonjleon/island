// Game page entry: store + connection + 2D renderer + input + HUD.
import { addChatCatalogue } from "../chat/i18n";
import { ChatLog, parseChatFrame } from "../chat/model";
import { initI18n, pageLanguage } from "../i18n";
import { loadBindings } from "../input/bindings";
import { InputController } from "../input/controller";
import { addInputCatalogue } from "../input/i18n";
import { menuFactory } from "../input/menu";
import { GameConnection } from "../net/connection";
import { PixiRenderer } from "../render2d/PixiRenderer";
import { GameStore } from "../state/store";
import { mountHud } from "../ui/Hud";
import { enterFullscreenOnFirstTap, onFullscreenChange } from "../ui/autoFullscreen";
import { addHudCatalogues } from "../ui/i18n";
import { csrfFromCookie } from "../ui/model";
import type { TFunction } from "i18next";

interface PageConfig { game: string; wsPath: string; seat: number | null; lang: string; lobbyUrl?: string; helpUrl?: string }

function wsUrl(path: string): string {
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${path}`;
}

/** A phone or tablet: the main pointer is a finger and there is no mouse. */
function touchFirst(): boolean {
  return matchMedia("(pointer: coarse)").matches && !matchMedia("(any-pointer: fine)").matches;
}

/** How far the HUD panels reach into the canvas (phones have little room to spare).
 * A panel across the middle of the screen pushes the island down or up; a corner panel
 * either does that or narrows the island from both sides, whichever costs less room.
 * The small round camera buttons may sit over the sea. */
function hudInsets(canvas: HTMLElement, hud: HTMLElement) {
  const box = canvas.getBoundingClientRect();
  let top = 0;
  let bottom = 0;
  let side = 0;
  const panels = hud.querySelectorAll<HTMLElement>(
    ".hud-clock, .hud-scores, .hud-bottom .hud-panel, .hud-bottom .hud-spectator");
  for (const el of panels) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const upper = r.top + r.height / 2 < box.top + box.height / 2;
    const down = upper ? r.bottom - box.top : box.bottom - r.top;
    const across = r.left - box.left < box.width / 3 && box.right - r.right < box.width / 3;
    const fromSide = Math.min(r.right - box.left, box.right - r.left);
    if (!across && fromSide / box.width < down / box.height) side = Math.max(side, fromSide);
    else if (upper) top = Math.max(top, down);
    else bottom = Math.max(bottom, down);
  }
  return { top, right: side, bottom, left: side };
}

async function main(): Promise<void> {
  const root = document.getElementById("game-root");
  const configEl = document.getElementById("game-config");
  if (!root || !configEl) return;
  const config = JSON.parse(configEl.textContent ?? "{}") as PageConfig;
  const i18n = await initI18n(pageLanguage());
  addInputCatalogue(i18n);
  addHudCatalogues(i18n);
  addChatCatalogue(i18n);
  const t = i18n.t.bind(i18n) as TFunction;

  root.innerHTML = "";
  const canvasHost = document.createElement("div");
  canvasHost.className = "game-canvas";
  const hudHost = document.createElement("div");
  hudHost.className = "game-hud";
  root.append(canvasHost, hudHost);

  const store = new GameStore();
  const chatLog = new ChatLog();
  const bindings = await loadBindings();
  let input: InputController | null = null;
  let hud: ReturnType<typeof mountHud> | null = null;
  const connection = new GameConnection({
    url: wsUrl(config.wsPath), lang: config.lang, store,
    onStatus: (s, info) => hud?.setLink(s, info),
    onReject: (reject, intent) => {
      input?.rejected(intent);
      hud?.notify(reject.code, reject.params);
    },
    onNotice: (code, params) => (code.startsWith("chat.") ? chatLog.refused(code, params) : hud?.notify(code, params)),
    onChat: (msg) => {
      const frame = parseChatFrame(msg);
      if (frame) chatLog.receive(frame);
    },
  });
  const renderer = new PixiRenderer();
  renderer.setFitInsets(() => hudInsets(canvasHost, hudHost));
  await renderer.mount(canvasHost);
  const controller = new InputController({
    store, renderer, bindings, now: () => connection.clock.now(),
    send: (intent) => connection.send(intent),
    onMode: (m) => hud?.setMode(m),
    onAction: (a) => {
      if (a === "open_trade") hud?.openTrade();
      if (a === "buy_dev_card") hud?.buyCard();
    },
    onRobber: (hex) => hud?.robberPicked(hex),
    showMenu: menuFactory(canvasHost, t),
  });
  input = controller;
  controller.attach(canvasHost);
  hud = mountHud(hudHost, {
    store, t, now: () => connection.clock.now(),
    send: (intent) => connection.send(intent),
    controls: {
      action: (a) => controller.action(a),
      setPaused: (p) => controller.setPaused(p),
      setBindings: (b) => controller.setBindings(b),
      fitView: () => renderer.fit(),
      startRobber: () => controller.startRobber(),
    },
    touch: touchFirst(),
    reconnect: () => connection.retryNow(),
    chat: { log: chatLog, send: (text) => connection.say(text) },
    bindings, csrfToken: csrfFromCookie(document.cookie), lobbyUrl: config.lobbyUrl ?? "/lobby/", helpUrl: config.helpUrl,
  });
  connection.start();
  // Full screen changes the room for the island a lot (and the HUD moves): show it all again.
  onFullscreenChange(() => renderer.fit());
  if (touchFirst()) enterFullscreenOnFirstTap();
  // The renderer follows its host's size itself (and keeps the camera centred).

  let lastFrame = performance.now();
  let fitted = false;
  const frame = (at: number) => {
    if (!fitted && store.state && store.board) {
      // Fit again once the HUD has drawn its panels, so the island starts clear of them.
      fitted = true;
      setTimeout(() => renderer.fit(), 300);
    }
    controller.tick(Math.min(100, at - lastFrame));
    lastFrame = at;
    renderer.update(store, connection.clock.now());
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  // For debugging and end-to-end tests.
  (window as unknown as { island: object }).island = { store, connection, renderer, input: controller, chat: chatLog };
}

void main();
