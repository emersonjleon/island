// Game page entry: store + connection + 2D renderer + input + HUD.
import { initI18n, pageLanguage } from "../i18n";
import { loadBindings } from "../input/bindings";
import { InputController } from "../input/controller";
import { addInputCatalogue } from "../input/i18n";
import { menuFactory } from "../input/menu";
import { GameConnection } from "../net/connection";
import { PixiRenderer } from "../render2d/PixiRenderer";
import { GameStore } from "../state/store";
import { mountHud } from "../ui/Hud";
import { addHudCatalogues } from "../ui/i18n";
import { csrfFromCookie } from "../ui/model";
import type { TFunction } from "i18next";

interface PageConfig { game: string; wsPath: string; seat: number | null; lang: string; lobbyUrl?: string }

function wsUrl(path: string): string {
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${path}`;
}

async function main(): Promise<void> {
  const root = document.getElementById("game-root");
  const configEl = document.getElementById("game-config");
  if (!root || !configEl) return;
  const config = JSON.parse(configEl.textContent ?? "{}") as PageConfig;
  const i18n = await initI18n(pageLanguage());
  addInputCatalogue(i18n);
  addHudCatalogues(i18n);
  const t = i18n.t.bind(i18n) as TFunction;

  root.innerHTML = "";
  const canvasHost = document.createElement("div");
  canvasHost.className = "game-canvas";
  const hudHost = document.createElement("div");
  hudHost.className = "game-hud";
  root.append(canvasHost, hudHost);

  const store = new GameStore();
  const bindings = await loadBindings();
  let input: InputController | null = null;
  let hud: ReturnType<typeof mountHud> | null = null;
  const connection = new GameConnection({
    url: wsUrl(config.wsPath), lang: config.lang, store,
    onStatus: (s) => hud?.setLink(s),
    onReject: (reject, intent) => {
      input?.rejected(intent);
      hud?.notify(reject.code, reject.params);
    },
    onNotice: (code, params) => hud?.notify(code, params),
  });
  const renderer = new PixiRenderer();
  await renderer.mount(canvasHost);
  const controller = new InputController({
    store, renderer, bindings, now: () => connection.clock.now(),
    send: (intent) => connection.send(intent),
    onMode: (m) => hud?.setMode(m),
    onAction: (a) => { if (a === "open_trade") hud?.openTrade(); },
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
    },
    bindings, csrfToken: csrfFromCookie(document.cookie), lobbyUrl: config.lobbyUrl ?? "/lobby/",
  });
  connection.start();
  window.addEventListener("resize", () => renderer.fit());

  let lastFrame = performance.now();
  const frame = (at: number) => {
    controller.tick(Math.min(100, at - lastFrame));
    lastFrame = at;
    renderer.update(store, connection.clock.now());
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  // For debugging and end-to-end tests.
  (window as unknown as { island: object }).island = { store, connection, renderer, input: controller };
}

void main();
