// The game HUD: DOM panels over the canvas (dice clock, players, hand and build
// buttons, bank trade, event log, notices, game over, key settings). It reads the
// store and sends intents; it never changes game state itself.
import type { TFunction } from "i18next";
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

import type { Action, Bindings } from "../input/bindings";
import type { ModeInfo } from "../input/controller";
import type { BuildKind, Intent, Resource } from "../protocol/types";
import { playerColour } from "../render2d/palette";
import type { GameStore } from "../state/store";
import "./hud.css";
import { cardCount, devPlayer, knightVictims } from "../state/devcards";
import { DevCardsDialog, VictimDialog } from "./DevCards";
import { Dialog, useEscape } from "./Dialog";
import { GuidePanel, HelpDialog } from "./Guide";
import { Die, ResIcon } from "./icons";
import { KeySettings } from "./KeySettings";
import { ResignDialog, StatsDialog, StatsPanel } from "./Stats";
import { othersOffers, playerTradesOn } from "../state/tradeboard";
import { TradeBoard } from "./TradeBoard";
import {
  MANY_PLAYERS, RESOURCES, canAfford, checkTrade, costOf, countdownShare, errorText, formatRes, handTotal, logLine,
  rollInterval, victoryTarget, visibleScoreSeats, type LogLine,
} from "./model";

export interface HudControls {
  /** Run an input action (build buttons call build_road etc.). */
  action(a: Action): void;
  /** Pause keyboard input while a dialog is open. */
  setPaused(paused: boolean): void;
  setBindings(b: Bindings): void;
  /** Show the whole island. */
  fitView(): void;
  /** Knight card: let the player pick the robber's hex on the board. */
  startRobber(): void;
}

export interface HudProps {
  store: GameStore;
  t: TFunction;
  now: () => number;
  send: (intent: Intent) => string | null;
  controls: HudControls;
  bindings: Bindings;
  csrfToken: string;
  lobbyUrl: string;
  /** The full rules page ("How to play"). */
  helpUrl?: string;
  /** A touch screen is the main pointer: show touch help, hide keyboard-only bits. */
  touch?: boolean;
}

/** What the page feeds the HUD from outside the store. */
export interface HudFeed {
  link: string;
  mode: ModeInfo | null;
}

export interface HudHandle {
  setLink(link: string): void;
  setMode(mode: ModeInfo | null): void;
  notify(code: string, params?: Record<string, unknown>): void;
  openTrade(): void;
  /** The player picked the robber's hex for a knight: play it (asking whom to rob if needed). */
  robberPicked(hex: number): void;
  /** Buy a development card (keyboard shortcut). */
  buyCard(): void;
}

const LOG_KEEP = 50;
const NOTICE_MS = 4000;
const TICK_MS = 200;

type Notice = { id: number; text: string };

export function mountHud(el: HTMLElement, props: HudProps): HudHandle {
  const handle: HudHandle = {
    setLink: () => {}, setMode: () => {}, notify: () => {}, openTrade: () => {}, robberPicked: () => {}, buyCard: () => {},
  };
  render(<Hud {...props} handle={handle} />, el);
  return handle;
}

function Hud(props: HudProps & { handle: HudHandle }) {
  const { store, t, handle } = props;
  const [, setVersion] = useState(0);
  const [, setClock] = useState(0);
  const [feed, setFeed] = useState<HudFeed>({ link: "connecting", mode: null });
  const [log, setLog] = useState<LogLine[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [dialog, setDialog] = useState<"trade" | "keys" | "dev" | "stats" | "resign" | "fullscreen" | "help" | null>(null);
  const [overHidden, setOverHidden] = useState(false);
  const [victim, setVictim] = useState<{ hex: number; victims: number[] } | null>(null);
  const [bindings, setBindings] = useState(props.bindings);

  useEffect(() => {
    let seq = -1;
    const name = (seat: number) => store.player(seat)?.name ?? "?";
    const off = store.subscribe(() => {
      setVersion((v) => v + 1);
      if (store.seq !== seq && store.lastEvents.length) {
        const lines = store.lastEvents.map((ev) => logLine(t, ev, name, store.seat)).filter((l): l is LogLine => !!l);
        if (lines.length) setLog((old) => [...old, ...lines].slice(-LOG_KEEP));
      }
      seq = store.seq;
    });
    const timer = setInterval(() => setClock((c) => c + 1), TICK_MS);
    return () => { off(); clearInterval(timer); };
  }, [store, t]);

  useEffect(() => {
    let next = 0;
    handle.setLink = (link) => setFeed((f) => ({ ...f, link }));
    handle.setMode = (mode) => setFeed((f) => ({ ...f, mode }));
    handle.notify = (code, params) => {
      const id = ++next;
      setNotices((n) => [...n.slice(-2), { id, text: errorText(t, code, params) }]);
      setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), NOTICE_MS);
    };
    handle.openTrade = () => setDialog((d) => (d === "trade" ? null : "trade"));
    handle.buyCard = () => props.send({ a: "buy_dev_card" });
    handle.robberPicked = (hex) => {
      const s = store.state;
      const seat = store.seat;
      if (!s || seat === null || !store.board) return;
      const robbable = knightVictims(store.board, s, hex, seat, store.settings).filter((v) => (store.player(v)?.hand_count ?? 1) > 0);
      if (robbable.length > 1) setVictim({ hex, victims: robbable });
      else props.send({ a: "play_dev_card", card: "knight", hex, ...(robbable.length ? { victim: robbable[0] } : {}) });
    };
  }, [handle, t, store, props]);

  useEffect(() => props.controls.setPaused(dialog !== null || victim !== null), [dialog, victim, props.controls]);

  const s = store.state;
  const seated = store.seat !== null;
  const finished = s?.phase === "finished";
  const resigned = seated && !!store.player(store.seat!)?.resigned;
  const playing = seated && !finished && !resigned;
  return (
    <div class={props.touch ? "hud touch" : "hud"}>
      <div class="hud-top-left">
        <DiceClock {...props} feed={feed} onResults={finished && overHidden ? () => setOverHidden(false) : undefined} />
        {s && <GuidePanel store={store} t={t} touch={!!props.touch} onHelp={() => setDialog("help")} />}
      </div>
      {s && (
        <Scores {...props} onStats={() => setDialog("stats")} onResign={playing ? () => setDialog("resign") : undefined} />
      )}
      <div class="hud-bottom">
        <div class="hud-slot-log">{s && <Log t={t} lines={log} />}</div>
        <div class="hud-slot-hand">
          {s && playing && (
            <HandBar {...props} onTrade={() => setDialog("trade")} onKeys={() => setDialog("keys")} onDev={() => setDialog("dev")} />
          )}
          {s && resigned && !finished && (
            <div class="hud-spectator hud-resigned">
              {t("hud:resign.done")} <a href={props.lobbyUrl}>{t("hud:resign.back")}</a>
            </div>
          )}
          {!seated && s && <div class="hud-spectator">{t("hud:spectator")}</div>}
        </div>
        <div class="hud-slot-camera">{s && <CameraButtons {...props} onFullscreenHelp={() => setDialog("fullscreen")} />}</div>
      </div>
      <div class="hud-notices" aria-live="polite">
        {notices.map((n) => <div key={n.id} class="hud-notice">{n.text}</div>)}
      </div>
      {dialog === "fullscreen" && <FullscreenHelp t={t} onClose={() => setDialog(null)} />}
      {dialog === "help" && s && (
        <HelpDialog store={store} t={t} touch={!!props.touch} helpUrl={props.helpUrl ?? "/how-to-play/"} onClose={() => setDialog(null)} />
      )}
      {dialog === "stats" && s && <StatsDialog store={store} t={t} now={props.now} onClose={() => setDialog(null)} />}
      {dialog === "resign" && s && playing && (
        <ResignDialog t={t} onClose={() => setDialog(null)} onConfirm={() => { props.send({ a: "resign" }); setDialog(null); }} />
      )}
      {dialog === "trade" && s && playing && <TradeDialog {...props} onClose={() => setDialog(null)} />}
      {dialog === "dev" && s && playing && (
        <DevCardsDialog store={store} t={t} now={props.now} send={props.send}
                        startRobber={() => props.controls.startRobber()} onClose={() => setDialog(null)} />
      )}
      {victim && s && (
        <VictimDialog store={store} t={t} hex={victim.hex} victims={victim.victims} send={props.send} onClose={() => setVictim(null)} />
      )}
      {dialog === "keys" && (
        <KeySettings
          t={t} bindings={bindings} csrfToken={props.csrfToken}
          onChange={(b) => { setBindings(b); props.controls.setBindings(b); }}
          onClose={() => setDialog(null)}
        />
      )}
      {finished && !overHidden && <GameOver {...props} onHide={() => setOverHidden(true)} />}
    </div>
  );
}

// ------------------------------------------------------------------ dice clock
function DiceClock(props: HudProps & { feed: HudFeed; onResults?: () => void }) {
  const { store, t, now, feed } = props;
  const s = store.state;
  let body;
  if (feed.link !== "open") {
    body = <span>{t(feed.link === "connecting" && !s ? "connecting" : "reconnecting")}</span>;
  } else if (!s) {
    body = <span>{t("loading")}</span>;
  } else if (feed.mode) {
    const help = !feed.mode.count ? "input:mode.none" : feed.mode.kind === "robber" ? "input:mode.robberHelp"
      : props.touch ? "input:mode.touchHelp" : "input:mode.help";
    body = (
      <>
        <span class="hud-mode"><strong>{t(`input:mode.${feed.mode.kind}`)}</strong> <span>{t(help)}</span></span>
        <button type="button" class="hud-cancel" onClick={() => props.controls.action("cancel")}>{t("hud:action.cancel")}</button>
      </>
    );
  } else if (s.phase === "finished") {
    body = (
      <>
        <span>{t("status.finished")}</span>
        {props.onResults && <button type="button" class="primary" onClick={props.onResults}>{t("hud:over.results")}</button>}
      </>
    );
  } else if (!s.clock_started) {
    body = <span>{t("status.setup")}</span>;
  } else {
    const n = now();
    const share = countdownShare(s.next_roll_at, n, rollInterval(store.settings));
    const secs = s.next_roll_at === null ? 0 : Math.max(0, Math.ceil((s.next_roll_at - n) / 1000));
    body = (
      <>
        <Ring share={share} label={String(secs)} title={t("hud:dice.next")} />
        {s.last_roll && (
          <span class="hud-dice" title={t("hud:dice.last")}>
            {s.last_roll.map((d, i) => <Die key={i} value={d} />)}
            <strong class="hud-sum">{s.last_roll.reduce((a, b) => a + b, 0)}</strong>
          </span>
        )}
        {s.dice_history.length > 1 && (
          <span class="hud-history" title={t("hud:dice.history")}>
            {s.dice_history.slice(-8, -1).reverse().map((d, i) => <span key={i} class={d === 7 ? "seven" : ""}>{d}</span>)}
          </span>
        )}
      </>
    );
  }
  return <div class="hud-panel hud-clock" role="status">{body}</div>;
}

function Ring({ share, label, title }: { share: number; label: string; title: string }) {
  const r = 16;
  const c = 2 * Math.PI * r;
  return (
    <svg class="hud-ring" width="40" height="40" viewBox="0 0 40 40" role="img" aria-label={`${title}: ${label}`}>
      <circle cx="20" cy="20" r={r} class="ring-bg" />
      <circle cx="20" cy="20" r={r} class="ring-fg" stroke-dasharray={`${c * share} ${c}`} transform="rotate(-90 20 20)" />
      <text x="20" y="25" text-anchor="middle">{label}</text>
    </svg>
  );
}

// ------------------------------------------------------------------ players
function smallScreen(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(max-width: 720px), (max-height: 500px)").matches;
}

function Scores({ store, t, onStats, onResign }: HudProps & { onStats(): void; onResign?: () => void }) {
  const s = store.state!;
  const target = victoryTarget(store.settings);
  const many = s.players.length > MANY_PLAYERS;
  const [folded, setFolded] = useState(smallScreen);
  const shown = new Set(visibleScoreSeats(s.players, store.seat, many && folded));
  return (
    <div class={`hud-panel hud-scores${many ? " many" : ""}`}>
      <h2>{t("hud:scores.title")}</h2>
      <ul>
        {s.players.filter((p) => shown.has(p.seat)).map((p) => {
          const cards = p.hand ? handTotal(p.hand) : p.hand_count;
          const road = s.longest_road?.lengths[String(p.seat)] ?? 0;
          const holds = s.longest_road?.holder === p.seat;
          const dev = s.dev_cards?.players[String(p.seat)];
          const army = s.dev_cards?.army === p.seat;
          return (
            <li key={p.seat} class={`${p.seat === store.seat ? "me" : ""}${p.resigned ? " resigned" : ""}`}>
              <Swatch colour={p.colour} />
              <span class="name">
                {p.name} {p.seat === store.seat && <small>{t("hud:scores.you")}</small>}
                {p.resigned && <small class="tag" title={t("hud:scores.resigned")}>⚑</small>}
              </span>
              {p.points !== undefined && (
                <span class="points">{target ? t("hud:scores.points", { points: p.points, target }) : p.points}</span>
              )}
              {cards !== undefined && (
                <span class="cards">
                  {t("hud:scores.cards", { count: cards })}
                  {road > 0 && <> · {t("hud:scores.road", { count: road })}</>}
                  {holds && <> · <strong class="award">{t("hud:scores.longest_road")}</strong></>}
                  {p.seat !== store.seat && cardCount(dev) > 0 && <> · {t("hud:scores.dev", { count: cardCount(dev) })}</>}
                  {(dev?.knights ?? 0) > 0 && <> · {t("hud:scores.knights", { count: dev!.knights })}</>}
                  {army && <> · <strong class="award">{t("hud:scores.largest_army")}</strong></>}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {many && (
        <button type="button" class="scores-fold" aria-expanded={!folded} onClick={() => setFolded((f) => !f)}>
          {folded ? t("hud:scores.show_all", { count: s.players.length }) : t("hud:scores.show_less")}
        </button>
      )}
      <div class="score-actions">
        <button type="button" class="stats-open" onClick={onStats} aria-label={t("hud:stats.open")} title={t("hud:stats.open")}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" /></svg>
          <span>{t("hud:stats.open")}</span>
        </button>
        {onResign && (
          <button type="button" class="resign-open" onClick={onResign} aria-label={t("hud:resign.open")} title={t("hud:resign.open")}>
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M5 22V3M5 4h12l-3 4 3 4H5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" /></svg>
            <span>{t("hud:resign.open")}</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ log
function Log({ t, lines }: { t: TFunction; lines: LogLine[] }) {
  if (!lines.length) return null;
  return (
    <div class="hud-panel hud-log">
      <h2>{t("hud:log.title")}</h2>
      <ol>{lines.slice(-6).map((l, i) => <li key={lines.length - 6 + i}>{l.text}</li>)}</ol>
    </div>
  );
}

// ------------------------------------------------------------------ hand + build
const BUILDS: { kind: BuildKind & ("road" | "settlement" | "city"); action: Action }[] = [
  { kind: "road", action: "build_road" },
  { kind: "settlement", action: "build_settlement" },
  { kind: "city", action: "build_city" },
];

function HandBar({ store, t, controls, touch, send, onTrade, onKeys, onDev }:
  HudProps & { onTrade(): void; onKeys(): void; onDev(): void }) {
  const me = store.player(store.seat!);
  const hand = me?.hand ?? {};
  const cardCost = costOf(store.settings, "dev_card" as BuildKind);
  const myCards = cardCount(devPlayer(store.state, store.seat));
  const deckLeft = store.state?.dev_cards?.deck_left ?? 0;
  const refill = (store.settings["dev_cards"] as { refill?: boolean } | undefined)?.refill !== false;
  const offerCount = othersOffers(store.state, store.seat).length;
  return (
    <div class="hud-panel hud-hand">
      <div class="cards" aria-label={t("hud:hand")}>
        {RESOURCES.map((r) => (
          <span key={r} class={`card res-${r}${(hand[r] ?? 0) === 0 ? " empty" : ""}`} title={t(`hud:res.${r}`)}>
            <ResIcon res={r} />
            <span class="count">{hand[r] ?? 0}</span>
            <span class="label">{t(`hud:res.${r}`)}</span>
          </span>
        ))}
      </div>
      <div class="actions">
        {BUILDS.map(({ kind, action }) => {
          const cost = costOf(store.settings, kind);
          const ok = canAfford(hand, cost);
          return (
            <button key={kind} type="button" class={ok ? "" : "short"} onClick={() => controls.action(action)}
                    title={t("hud:build.cost", { res: formatRes(t, cost) })}>
              {t(`hud:build.${kind}`)}
            </button>
          );
        })}
        <button type="button" class={canAfford(hand, cardCost) && (deckLeft > 0 || refill) ? "buy-card" : "buy-card short"}
                onClick={() => send({ a: "buy_dev_card" })}
                title={t("hud:dev.buyCost", { res: formatRes(t, cardCost), left: deckLeft })}>
          {t("hud:dev.buy")}
        </button>
        {myCards > 0 && <button type="button" class="dev-open" onClick={onDev}>{t("hud:dev.open", { count: myCards })}</button>}
        <button type="button" class="trade-open" onClick={onTrade}>
          {t("hud:trade.open")}
          {offerCount > 0 && <span class="badge" title={t("hud:offers.waiting", { count: offerCount })}>{offerCount}</span>}
        </button>
        {!touch && <button type="button" class="quiet" onClick={onKeys}>{t("hud:keys.open")}</button>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ camera
/** Buttons for what keys and the wheel do on a desktop: centre on the settler, show the island. */
function CameraButtons({ store, t, controls, touch, onFullscreenHelp }: HudProps & { onFullscreenHelp(): void }) {
  const full = useFullscreen();
  const toggle = () => {
    if (full.supported) full.toggle();
    else onFullscreenHelp();
  };
  return (
    <div class="hud-camera">
      {(full.supported || (touch && !full.standalone)) && (
        <button type="button" class="fullscreen" onClick={toggle} aria-pressed={full.active}
                aria-label={t(full.active ? "hud:camera.exitFullscreen" : "hud:camera.fullscreen")}
                title={t(full.active ? "hud:camera.exitFullscreen" : "hud:camera.fullscreen")}>
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <rect x="2.5" y="5" width="19" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8" />
            <path d={full.active ? "M10 8.5v3H7M14 15.5v-3h3" : "M7 11.5v-3h3M17 12.5v3h-3"}
                  fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      )}
      {store.seat !== null && (
        <button type="button" onClick={() => controls.action("center_selected")} aria-label={t("hud:camera.center")} title={t("hud:camera.center")}>
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="currentColor" /><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2" /></svg>
        </button>
      )}
      <button type="button" onClick={() => controls.fitView()} aria-label={t("hud:camera.fit")} title={t("hud:camera.fit")}>
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" fill="none" stroke="currentColor" stroke-width="2" /></svg>
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ full screen
type FsDoc = Document & { webkitFullscreenEnabled?: boolean; webkitFullscreenElement?: Element | null; webkitExitFullscreen?: () => void };
type FsEl = HTMLElement & { webkitRequestFullscreen?: () => void };

/** Full screen hides the browser's own bars, which on phones cover part of the game. */
function useFullscreen() {
  const doc = document as FsDoc;
  const supported = !!(doc.fullscreenEnabled || doc.webkitFullscreenEnabled);
  const current = () => !!(doc.fullscreenElement || doc.webkitFullscreenElement);
  const [active, setActive] = useState(current());
  useEffect(() => {
    const on = () => setActive(current());
    document.addEventListener("fullscreenchange", on);
    document.addEventListener("webkitfullscreenchange", on);
    return () => { document.removeEventListener("fullscreenchange", on); document.removeEventListener("webkitfullscreenchange", on); };
  }, []);
  const toggle = () => {
    if (current()) {
      if (doc.exitFullscreen) void doc.exitFullscreen().catch(() => {});
      else doc.webkitExitFullscreen?.();
      return;
    }
    const el = document.documentElement as FsEl;
    if (el.requestFullscreen) void el.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
    else el.webkitRequestFullscreen?.();
  };
  const standalone = matchMedia("(display-mode: standalone), (display-mode: fullscreen)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return { supported, active, toggle, standalone };
}

/** Phones without the full screen API (iPhone): the game can be added to the home screen. */
function FullscreenHelp({ t, onClose }: { t: TFunction; onClose(): void }) {
  useEscape(onClose);
  return (
    <Dialog title={t("hud:fullscreen.title")} t={t} closeKey="hud:stats.close" onClose={onClose}>
      <p class="resign-body">{t("hud:fullscreen.body")}</p>
    </Dialog>
  );
}

// ------------------------------------------------------------------ trade
function TradeDialog(props: HudProps & { onClose(): void }) {
  const { store, t, onClose } = props;
  const players = playerTradesOn(store.settings);
  const [tab, setTab] = useState<"bank" | "players">(() => (players && othersOffers(store.state, store.seat).length ? "players" : "bank"));
  useEscape(onClose);
  return (
    <Dialog title={t(players ? "hud:trade.titleAll" : "hud:trade.title")} onClose={onClose} t={t} closeKey="hud:trade.close">
      {players && (
        <div class="tabs" role="tablist">
          <button type="button" role="tab" class="tab-bank" aria-selected={tab === "bank"} onClick={() => setTab("bank")}>
            {t("hud:trade.bankTab")}
          </button>
          <button type="button" role="tab" class="tab-players" aria-selected={tab === "players"} onClick={() => setTab("players")}>
            {t("hud:trade.playersTab")}
          </button>
        </div>
      )}
      {tab === "players" && players ? <TradeBoard {...props} /> : <BankTrade {...props} />}
    </Dialog>
  );
}

function BankTrade({ store, t, send, onClose }: HudProps & { onClose(): void }) {
  const s = store.state!;
  const seat = store.seat!;
  const hand = store.player(seat)?.hand ?? {};
  const [give, setGive] = useState<Resource>(RESOURCES.reduce((a, r) => ((hand[r] ?? 0) > (hand[a] ?? 0) ? r : a), "lumber" as Resource));
  const [get, setGet] = useState<Resource>("ore");
  const [n, setN] = useState(1);
  const check = checkTrade(store.settings, store.board!, s, seat, give, get, n);
  const submit = () => {
    send({ a: "bank_trade", give: { [give]: check.ratio * n }, get: { [get]: n } });
    onClose();
  };
  return (
    <>
      <div class="trade-grid">
        <h3>{t("hud:trade.give")}</h3>
        <div class="choices">
          {RESOURCES.map((r) => (
            <button key={r} type="button" aria-pressed={give === r} class={`card res-${r}`} onClick={() => setGive(r)}>
              <ResIcon res={r} />
              <span class="count">{hand[r] ?? 0}</span>
              <span class="label">{t(`hud:res.${r}`)}</span>
              <small>{t("hud:trade.ratio", { ratio: checkTrade(store.settings, store.board!, s, seat, r, get, 1).ratio })}</small>
            </button>
          ))}
        </div>
        <h3>{t("hud:trade.get")}</h3>
        <div class="choices">
          {RESOURCES.map((r) => (
            <button key={r} type="button" aria-pressed={get === r} class={`card res-${r}`} onClick={() => setGet(r)}>
              <ResIcon res={r} />
              <span class="label">{t(`hud:res.${r}`)}</span>
            </button>
          ))}
        </div>
      </div>
      <div class="trade-amount">
        <button type="button" onClick={() => setN(Math.max(1, n - 1))} aria-label="−">−</button>
        <span>{t("hud:trade.summary", { give: formatRes(t, { [give]: check.ratio * n }), get: formatRes(t, { [get]: n }) })}</span>
        <button type="button" onClick={() => setN(n + 1)} aria-label="+">+</button>
      </div>
      {!check.ok && check.reason && <p class="trade-why">{errorText(t, check.reason)}</p>}
      <div class="dialog-buttons">
        <button type="button" class="primary" disabled={!check.ok} onClick={submit}>{t("hud:trade.confirm")}</button>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ game over
function GameOver({ store, t, lobbyUrl, now, onHide }: HudProps & { onHide(): void }) {
  const s = store.state!;
  const winner = s.winner === null ? undefined : store.player(s.winner);
  return (
    <div class="hud-overlay" role="dialog" aria-modal="true" aria-labelledby="game-over-title">
      <div class="hud-dialog hud-over">
        <svg class="trophy" viewBox="0 0 64 64" width="64" height="64" aria-hidden="true">
          <path d="M18 8h28v14a14 14 0 0 1-28 0z" fill="#f0c94f" stroke="#a67c1a" stroke-width="2.5" />
          <path d="M18 13H9v4a9 9 0 0 0 9 9M46 13h9v4a9 9 0 0 1-9 9" fill="none" stroke="#a67c1a" stroke-width="3" />
          <path d="M28 36h8v10h-8z" fill="#d9a92f" /><rect x="20" y="46" width="24" height="8" rx="2" fill="#7a5232" />
          <path d="M26 14v8" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity="0.6" />
        </svg>
        <h2 id="game-over-title">{t("hud:over.title")}</h2>
        <p class="winner">
          {!winner ? t("hud:over.noWinner") : winner.seat === store.seat ? t("hud:over.youWin") : t("hud:over.winner", { name: winner.name })}
        </p>
        {s.end_reason === "resign" && <p class="over-reason">{t("hud:over.byResign")}</p>}
        <StatsPanel store={store} t={t} now={now} />
        <div class="over-buttons">
          <button type="button" onClick={onHide}>{t("hud:over.showBoard")}</button>
          <a class="button primary" href={lobbyUrl}>{t("hud:over.back")}</a>
        </div>
      </div>
    </div>
  );
}

function Swatch({ colour }: { colour: string }) {
  return <span class="swatch" style={{ background: `#${playerColour(colour).toString(16).padStart(6, "0")}` }} />;
}
