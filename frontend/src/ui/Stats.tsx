// Game statistics (how each player got their points, the score over time, what the
// dice paid) and the resign confirmation. The panel is shown in a dialog during the
// game and inside the game-over screen.
import type { TFunction } from "i18next";

import type { GameStateView, PlayerView } from "../protocol/types";
import { playerColour } from "../render2d/palette";
import { POINT_SOURCES, type PointSource, clockText, pointsBreakdown, producedTotal, scoreLine, stepPath } from "../state/stats";
import type { GameStore } from "../state/store";
import { Dialog, useEscape } from "./Dialog";
import { ResIcon } from "./icons";
import { RESOURCES, victoryTarget } from "./model";

const SOURCE_CLASS: Record<PointSource, string> = {
  settlement: "src-settlement", city: "src-city", megacity: "src-megacity",
  longest_road: "src-road", largest_army: "src-army", victory_point: "src-vp",
};

export function colourHex(colour: string): string {
  return `#${playerColour(colour).toString(16).padStart(6, "0")}`;
}

function ranked(state: GameStateView): PlayerView[] {
  return [...state.players].sort((a, b) => (b.points ?? -1) - (a.points ?? -1) || a.seat - b.seat);
}

export function StatsPanel({ store, t, now }: { store: GameStore; t: TFunction; now: () => number }) {
  const s = store.state;
  if (!s) return null;
  const until = s.finished_at ?? Math.max(s.now, now());
  return (
    <div class="stats">
      <Breakdown store={store} t={t} state={s} />
      <ScoreChart store={store} t={t} state={s} until={until} />
      <Production store={store} t={t} state={s} />
    </div>
  );
}

// ------------------------------------------------------------------ points by source
function Breakdown({ store, t, state }: { store: GameStore; t: TFunction; state: GameStateView }) {
  const target = victoryTarget(store.settings) ?? 10;
  const players = ranked(state);
  const scale = Math.max(target, ...players.map((p) => p.points ?? 0));
  const used = new Set<PointSource>();
  const rows = players.map((p) => {
    const parts = p.points === undefined ? [] : pointsBreakdown(store.settings, state, p.seat);
    parts.forEach((x) => used.add(x.source));
    return { p, parts };
  });
  return (
    <section>
      <h3>{t("hud:stats.points")}</h3>
      <ul class="stats-legend">
        {POINT_SOURCES.filter((src) => used.has(src)).map((src) => (
          <li key={src}><span class={`stats-key ${SOURCE_CLASS[src]}`} aria-hidden="true" />{t(`hud:stats.label.${src}`)}</li>
        ))}
      </ul>
      <ul class="stats-players">
        {rows.map(({ p, parts }) => (
          <li key={p.seat} class={p.resigned ? "resigned" : ""}>
            <div class="who">
              <span class="swatch" style={{ background: colourHex(p.colour) }} />
              <span class="name">{p.seat === store.seat ? t("hud:you") : p.name}</span>
              {p.resigned && <small class="tag">{t("hud:stats.resigned")}</small>}
              <strong class="total">{p.points ?? "?"}</strong>
            </div>
            {p.points === undefined ? (
              <p class="muted">{t("hud:stats.hidden")}</p>
            ) : (
              <>
                <div class="stats-bar" role="img" aria-label={t("hud:stats.pointsOf", { name: p.name, count: p.points })}>
                  {parts.map((x) => (
                    <span key={x.source} class={SOURCE_CLASS[x.source]} title={t(`hud:stats.label.${x.source}`)}
                          style={{ width: `${(100 * x.points) / scale}%` }} />
                  ))}
                  <span class="target" style={{ left: `${(100 * target) / scale}%` }} />
                </div>
                <p class="parts">
                  {parts.length === 0 ? t("hud:stats.noPoints")
                    : parts.map((x) => (
                      <span key={x.source} class="part">
                        <span class={`stats-key ${SOURCE_CLASS[x.source]}`} aria-hidden="true" />
                        {t(`hud:stats.part.${x.source}`, { count: x.count, points: x.points })}
                      </span>
                    ))}
                </p>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------------ score over time
const W = 320;
const H = 150;
const PAD = { l: 22, r: 8, t: 8, b: 20 };

function ScoreChart({ store, t, state, until }: { store: GameStore; t: TFunction; state: GameStateView; until: number }) {
  const target = victoryTarget(store.settings) ?? 10;
  const lines = state.players
    .map((p) => ({ p, line: scoreLine(state, p.seat, until) }))
    .filter((l) => l.line.length > 0);
  if (!lines.length) return null;
  const end = Math.max(until, 1000, ...lines.map((l) => l.line[l.line.length - 1]![0]));
  const top = Math.max(target, ...lines.flatMap((l) => l.line.map(([, p]) => p)));
  const x = (ms: number) => PAD.l + ((W - PAD.l - PAD.r) * ms) / end;
  const y = (p: number) => H - PAD.b - ((H - PAD.t - PAD.b) * p) / top;
  const step = top > 12 ? 4 : 2;
  const ticks = Array.from({ length: Math.floor(top / step) + 1 }, (_, i) => i * step);
  return (
    <section>
      <h3>{t("hud:stats.timeline")}</h3>
      <svg class="stats-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("hud:stats.timeline")}>
        {ticks.map((p) => (
          <g key={p}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(p)} y2={y(p)} class="grid" />
            <text x={PAD.l - 5} y={y(p) + 3.5} text-anchor="end">{p}</text>
          </g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(target)} y2={y(target)} class="goal" />
        {!ticks.includes(target) && <text x={PAD.l - 5} y={y(target) + 3.5} text-anchor="end" class="goal-label">{target}</text>}
        <text x={PAD.l} y={H - 5} text-anchor="start">0:00</text>
        <text x={W - PAD.r} y={H - 5} text-anchor="end">{clockText(end)}</text>
        {lines.map(({ p, line }) => <path key={`u${p.seat}`} d={stepPath(line, x, y)} class="line-under" />)}
        {lines.map(({ p, line }) => (
          <path key={p.seat} d={stepPath(line, x, y)} class={p.resigned ? "line resigned" : "line"}
                style={{ stroke: colourHex(p.colour) }} />
        ))}
      </svg>
    </section>
  );
}

// ------------------------------------------------------------------ dice production
function Production({ store, t, state }: { store: GameStore; t: TFunction; state: GameStateView }) {
  const produced = state.stats?.produced ?? {};
  const players = ranked(state).filter((p) => produced[String(p.seat)] !== undefined);
  if (!players.length) return null;
  return (
    <section>
      <h3>{t("hud:stats.produced")}</h3>
      <ul class="stats-produced">
        {players.map((p) => {
          const got = produced[String(p.seat)] ?? {};
          return (
            <li key={p.seat}>
              <span class="swatch" style={{ background: colourHex(p.colour) }} />
              <span class="name">{p.seat === store.seat ? t("hud:you") : p.name}</span>
              <span class="res">
                {RESOURCES.filter((r) => (got[r] ?? 0) > 0).map((r) => (
                  <span key={r} class={`mini res-${r}`} title={t(`hud:res.${r}`)}><ResIcon res={r} />{got[r]}</span>
                ))}
              </span>
              <strong>{producedTotal(got)}</strong>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------------ dialogs
export function StatsDialog(props: { store: GameStore; t: TFunction; now: () => number; onClose(): void }) {
  useEscape(props.onClose);
  return (
    <Dialog title={props.t("hud:stats.title")} t={props.t} closeKey="hud:stats.close" onClose={props.onClose}>
      <StatsPanel store={props.store} t={props.t} now={props.now} />
    </Dialog>
  );
}

export function ResignDialog({ t, onConfirm, onClose }: { t: TFunction; onConfirm(): void; onClose(): void }) {
  useEscape(onClose);
  return (
    <Dialog title={t("hud:resign.title")} t={t} closeKey="hud:stats.close" onClose={onClose}>
      <p class="resign-body">{t("hud:resign.body")}</p>
      <div class="dialog-buttons">
        <button type="button" onClick={onClose}>{t("hud:resign.cancel")}</button>
        <button type="button" class="danger" onClick={onConfirm}>{t("hud:resign.confirm")}</button>
      </div>
    </Dialog>
  );
}
