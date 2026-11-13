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
import { Dialog, useEscape } from "./Dialog";
import { KeySettings } from "./KeySettings";
import {
  RESOURCES, canAfford, checkTrade, costOf, countdownShare, errorText, formatRes, handTotal, logLine,
  rollInterval, victoryTarget, type LogLine,
} from "./model";

export interface HudControls {
  /** Run an input action (build buttons call build_road etc.). */
  action(a: Action): void;
  /** Pause keyboard input while a dialog is open. */
  setPaused(paused: boolean): void;
  setBindings(b: Bindings): void;
  /** Show the whole island. */
  fitView(): void;
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
}

const LOG_KEEP = 50;
const NOTICE_MS = 4000;
const TICK_MS = 200;

type Notice = { id: number; text: string };

export function mountHud(el: HTMLElement, props: HudProps): HudHandle {
  const handle: HudHandle = { setLink: () => {}, setMode: () => {}, notify: () => {}, openTrade: () => {} };
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
  const [dialog, setDialog] = useState<"trade" | "keys" | null>(null);
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
  }, [handle, t]);

  useEffect(() => props.controls.setPaused(dialog !== null), [dialog, props.controls]);

  const s = store.state;
  const seated = store.seat !== null;
  const finished = s?.phase === "finished";
  return (
    <div class={props.touch ? "hud touch" : "hud"}>
      <DiceClock {...props} feed={feed} />
      {s && <Scores {...props} />}
      <div class="hud-bottom">
        <div class="hud-slot-log">{s && <Log t={t} lines={log} />}</div>
        <div class="hud-slot-hand">
          {s && seated && !finished && (
            <HandBar {...props} onTrade={() => setDialog("trade")} onKeys={() => setDialog("keys")} />
          )}
          {!seated && s && <div class="hud-spectator">{t("hud:spectator")}</div>}
        </div>
        <div class="hud-slot-camera">{s && <CameraButtons {...props} />}</div>
      </div>
      <div class="hud-notices" aria-live="polite">
        {notices.map((n) => <div key={n.id} class="hud-notice">{n.text}</div>)}
      </div>
      {dialog === "trade" && s && seated && <TradeDialog {...props} onClose={() => setDialog(null)} />}
      {dialog === "keys" && (
        <KeySettings
          t={t} bindings={bindings} csrfToken={props.csrfToken}
          onChange={(b) => { setBindings(b); props.controls.setBindings(b); }}
          onClose={() => setDialog(null)}
        />
      )}
      {finished && <GameOver {...props} />}
    </div>
  );
}

// ------------------------------------------------------------------ dice clock
function DiceClock(props: HudProps & { feed: HudFeed }) {
  const { store, t, now, feed } = props;
  const s = store.state;
  let body;
  if (feed.link !== "open") {
    body = <span>{t(feed.link === "connecting" && !s ? "connecting" : "reconnecting")}</span>;
  } else if (!s) {
    body = <span>{t("loading")}</span>;
  } else if (feed.mode) {
    const help = !feed.mode.count ? "input:mode.none" : props.touch ? "input:mode.touchHelp" : "input:mode.help";
    body = (
      <>
        <span class="hud-mode"><strong>{t(`input:mode.${feed.mode.kind}`)}</strong> <span>{t(help)}</span></span>
        <button type="button" class="hud-cancel" onClick={() => props.controls.action("cancel")}>{t("hud:action.cancel")}</button>
      </>
    );
  } else if (s.phase === "finished") {
    body = <span>{t("status.finished")}</span>;
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
            {s.last_roll.map((d, i) => <span key={i} class="die">{d}</span>)}
            <strong>= {s.last_roll.reduce((a, b) => a + b, 0)}</strong>
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
function Scores({ store, t }: HudProps) {
  const s = store.state!;
  const target = victoryTarget(store.settings);
  return (
    <div class="hud-panel hud-scores">
      <h2>{t("hud:scores.title")}</h2>
      <ul>
        {s.players.map((p) => {
          const cards = p.hand ? handTotal(p.hand) : p.hand_count;
          const road = s.longest_road?.lengths[String(p.seat)] ?? 0;
          const holds = s.longest_road?.holder === p.seat;
          return (
            <li key={p.seat} class={p.seat === store.seat ? "me" : ""}>
              <Swatch colour={p.colour} />
              <span class="name">{p.name} {p.seat === store.seat && <small>{t("hud:scores.you")}</small>}</span>
              {p.points !== undefined && (
                <span class="points">{target ? t("hud:scores.points", { points: p.points, target }) : p.points}</span>
              )}
              {cards !== undefined && (
                <span class="cards">
                  {t("hud:scores.cards", { count: cards })}
                  {road > 0 && <> · {t("hud:scores.road", { count: road })}</>}
                  {holds && <> · <strong class="award">{t("hud:scores.longest_road")}</strong></>}
                </span>
              )}
            </li>
          );
        })}
      </ul>
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

function HandBar({ store, t, controls, touch, onTrade, onKeys }: HudProps & { onTrade(): void; onKeys(): void }) {
  const me = store.player(store.seat!);
  const hand = me?.hand ?? {};
  return (
    <div class="hud-panel hud-hand">
      <div class="cards" aria-label={t("hud:hand")}>
        {RESOURCES.map((r) => (
          <span key={r} class={`card res-${r}${(hand[r] ?? 0) === 0 ? " empty" : ""}`} title={t(`hud:res.${r}`)}>
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
        <button type="button" onClick={onTrade}>{t("hud:trade.open")}</button>
        {!touch && <button type="button" class="quiet" onClick={onKeys}>{t("hud:keys.open")}</button>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ camera
/** Buttons for what keys and the wheel do on a desktop: centre on the settler, show the island. */
function CameraButtons({ store, t, controls }: HudProps) {
  return (
    <div class="hud-camera">
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

// ------------------------------------------------------------------ trade
function TradeDialog({ store, t, send, onClose }: HudProps & { onClose(): void }) {
  const s = store.state!;
  const seat = store.seat!;
  const hand = store.player(seat)?.hand ?? {};
  const [give, setGive] = useState<Resource>(RESOURCES.reduce((a, r) => ((hand[r] ?? 0) > (hand[a] ?? 0) ? r : a), "lumber" as Resource));
  const [get, setGet] = useState<Resource>("ore");
  const [n, setN] = useState(1);
  useEscape(onClose);
  const check = checkTrade(store.settings, store.board!, s, seat, give, get, n);
  const submit = () => {
    send({ a: "bank_trade", give: { [give]: check.ratio * n }, get: { [get]: n } });
    onClose();
  };
  return (
    <Dialog title={t("hud:trade.title")} onClose={onClose} t={t} closeKey="hud:trade.close">
      <div class="trade-grid">
        <h3>{t("hud:trade.give")}</h3>
        <div class="choices">
          {RESOURCES.map((r) => (
            <button key={r} type="button" aria-pressed={give === r} class={`card res-${r}`} onClick={() => setGive(r)}>
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
    </Dialog>
  );
}

// ------------------------------------------------------------------ game over
function GameOver({ store, t, lobbyUrl }: HudProps) {
  const s = store.state!;
  const winner = s.winner === null ? undefined : store.player(s.winner);
  const ranked = [...s.players].sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
  return (
    <div class="hud-overlay" role="dialog" aria-modal="true" aria-labelledby="game-over-title">
      <div class="hud-dialog">
        <h2 id="game-over-title">{t("hud:over.title")}</h2>
        <p class="winner">
          {!winner ? t("hud:over.noWinner") : winner.seat === store.seat ? t("hud:over.youWin") : t("hud:over.winner", { name: winner.name })}
        </p>
        <ol class="final">
          {ranked.map((p) => (
            <li key={p.seat}><Swatch colour={p.colour} /> {p.name} <strong>{p.points ?? "–"}</strong></li>
          ))}
        </ol>
        <a class="button primary" href={lobbyUrl}>{t("hud:over.back")}</a>
      </div>
    </div>
  );
}

function Swatch({ colour }: { colour: string }) {
  return <span class="swatch" style={{ background: `#${playerColour(colour).toString(16).padStart(6, "0")}` }} />;
}
