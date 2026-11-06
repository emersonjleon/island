// Pure HUD helpers: costs, trade ratios, the event log and notices. No DOM here,
// so they are unit-tested directly; the Preact components only display them.
import type { TFunction } from "i18next";

import type { BoardMsg, BuildKind, GameEvent, GameStateView, ResMap, Resource } from "../protocol/types";

export const RESOURCES: Resource[] = ["lumber", "brick", "wool", "grain", "ore", "fish"];

type Settings = Record<string, unknown>;

function dig(o: unknown, ...path: string[]): unknown {
  let cur = o;
  for (const k of path) cur = cur && typeof cur === "object" ? (cur as Record<string, unknown>)[k] : undefined;
  return cur;
}

export function costOf(settings: Settings, kind: BuildKind): ResMap {
  return (dig(settings, "economy", "costs", kind) as ResMap | undefined) ?? {};
}

export function victoryTarget(settings: Settings): number | null {
  const v = dig(settings, "victory", "target");
  return typeof v === "number" ? v : null;
}

export function canAfford(hand: ResMap | undefined, cost: ResMap): boolean {
  return Object.entries(cost).every(([r, n]) => (hand?.[r as Resource] ?? 0) >= (n ?? 0));
}

export function handTotal(hand: ResMap | undefined): number {
  return Object.values(hand ?? {}).reduce((a, n) => a + (n ?? 0), 0);
}

/** Harbors where ``seat`` has a finished building (indexes into board.harbors). */
export function ownedHarbors(board: BoardMsg, state: GameStateView, seat: number): number[] {
  const mine = new Set(state.buildings.filter((b) => b.seat === seat).map((b) => b.vertex));
  return board.harbors.flatMap((h, i) => (h.vertices.some((v) => mine.has(v)) ? [i] : []));
}

/** The best ratio ``seat`` gets when giving ``give`` (mirrors engine/rules/trade.py best_ratio). */
export function bestRatio(settings: Settings, board: BoardMsg, state: GameStateView, seat: number, give: Resource): number {
  let ratio = (dig(settings, "economy", "trade", "bank_ratio") as number | undefined) ?? 4;
  if (dig(settings, "trading", "harbor_trade") === false) return ratio;
  for (const i of ownedHarbors(board, state, seat)) {
    const h = board.harbors[i]!;
    if (h.resource === null || h.resource === give) ratio = Math.min(ratio, h.ratio);
  }
  return ratio;
}

export interface TradeCheck { ok: boolean; reason?: string }

/** Client-side pre-check of a bank trade; the server has the final word. */
export function checkTrade(
  settings: Settings, board: BoardMsg, state: GameStateView, seat: number,
  give: Resource, get: Resource, n: number,
): TradeCheck & { ratio: number } {
  const ratio = bestRatio(settings, board, state, seat, give);
  const me = state.players.find((p) => p.seat === seat);
  if (give === get) return { ok: false, reason: "trade.same_resource", ratio };
  if (me && !me.setup.done && dig(settings, "setup", "bank_trade_during_setup") === false) {
    return { ok: false, reason: "trade.setup_forbidden", ratio };
  }
  if ((me?.hand?.[give] ?? 0) < ratio * n) return { ok: false, reason: "trade.cannot_afford", ratio };
  if ((state.bank[get] ?? Infinity) < n) return { ok: false, reason: "trade.bank_empty", ratio };
  return { ok: true, ratio };
}

/** "2 lumber, 1 ore" in the page language. */
export function formatRes(t: TFunction, m: ResMap | undefined): string {
  return RESOURCES.filter((r) => (m?.[r] ?? 0) > 0)
    .map((r) => t("hud:resCount", { count: m![r], res: t(`hud:res.${r}`) }))
    .join(", ");
}

/** Translate a reject code; unknown codes fall back to a generic line. */
export function errorText(t: TFunction, code: string, params: Record<string, unknown> = {}): string {
  const key = `errors:${code}`;
  const text = t(key, { ...params, defaultValue: "" });
  return text || t("errors:generic", { code });
}

export interface LogLine { text: string; seat: number | null }

/** One log line per interesting event (settler steps, hands, points etc. are left out). */
export function logLine(
  t: TFunction, ev: GameEvent, name: (seat: number) => string, viewer: number | null,
): LogLine | null {
  const seat = typeof ev.seat === "number" ? ev.seat : null;
  const who = seat === null ? "" : seat === viewer ? t("hud:you") : name(seat);
  const kindName = (k: unknown) => t(`hud:kind.${String(k)}`);
  switch (ev.k) {
    case "clock_started": return { text: t("events:clock_started"), seat: null };
    case "dice_rolled": return { text: t("events:dice_rolled", { sum: ev.sum }), seat: null };
    case "produced": {
      const gains = (ev.gains ?? {}) as Record<string, ResMap>;
      const mine = viewer === null ? undefined : gains[String(viewer)];
      if (mine && handTotal(mine) > 0) return { text: t("events:produced_you", { res: formatRes(t, mine) }), seat: viewer };
      if (!Object.values(gains).some((g) => handTotal(g) > 0)) return { text: t("events:produced_none"), seat: null };
      return null;
    }
    case "robber_moved": return { text: t("events:robber_moved"), seat: null };
    case "robber_stole": {
      const lost = ev.lost as ResMap | undefined;
      return { text: t("events:robber_stole", { who, res: lost ? formatRes(t, lost) : "" }), seat };
    }
    case "built": return { text: t("events:built", { who, kind: kindName(ev.kind) }), seat };
    case "construction_cancelled":
      return { text: t("events:construction_cancelled", { who, reason: t(`events:reason.${String(ev.reason)}`) }), seat };
    case "setup_complete": return { text: t("events:setup_complete", { who }), seat };
    case "starting_resources": {
      const g = ev.gained as ResMap | undefined;
      return handTotal(g) > 0 ? { text: t("events:starting_resources", { who, res: formatRes(t, g) }), seat } : null;
    }
    case "traded": return {
      text: t("events:traded", { who, give: formatRes(t, ev.give as ResMap), get: formatRes(t, ev.get as ResMap) }), seat,
    };
    case "game_over": return {
      text: ev.winner === null ? t("events:game_over_none")
        : ev.winner === viewer ? t("events:game_over_you") : t("events:game_over", { who: name(ev.winner as number) }),
      seat: null,
    };
    default: return null;
  }
}

/** Share of the roll interval still to go (1 = just rolled, 0 = rolling now). */
export function countdownShare(nextRollAt: number | null, now: number, intervalMs: number | null): number {
  if (nextRollAt === null || !intervalMs) return 0;
  return Math.max(0, Math.min(1, (nextRollAt - now) / intervalMs));
}

export function rollInterval(settings: Settings): number | null {
  const v = dig(settings, "clock", "roll_interval_ms");
  return typeof v === "number" ? v : null;
}

const ARROWS: Record<string, string> = { ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→" };
const NAMED: Record<string, string> = { Equal: "=", Minus: "-", NumpadAdd: "Num +", NumpadSubtract: "Num -", NumpadEnter: "Num Enter", Escape: "Esc" };

/** "Shift+KeyW" -> "Shift + W", "ArrowUp" -> "↑", "Digit1" -> "1". */
export function prettyCombo(combo: string): string {
  return combo.split("+").map((p) => {
    if (ARROWS[p]) return ARROWS[p];
    if (NAMED[p]) return NAMED[p];
    if (/^Key[A-Z]$/.test(p)) return p.slice(3);
    if (/^Digit\d$/.test(p)) return p.slice(5);
    return p;
  }).join(" + ");
}

/** The Django CSRF token from the csrftoken cookie ("" when absent). */
export function csrfFromCookie(cookie: string): string {
  const m = cookie.split(/;\s*/).find((c) => c.startsWith("csrftoken="));
  return m ? decodeURIComponent(m.slice("csrftoken=".length)) : "";
}
