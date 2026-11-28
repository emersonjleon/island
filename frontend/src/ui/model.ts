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
const AGE_ROMAN = ["I", "II", "III"];

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
  // "You ..." lines have their own wording where the language needs it (Spanish verbs agree with "tú").
  const tw = (key: string, params: Record<string, unknown>) =>
    t(seat !== null && seat === viewer ? [`events:${key}_you`, `events:${key}`] : `events:${key}`, params);
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
    case "settlers_gathered": {
      const mine = viewer === null ? undefined : ((ev.gains ?? {}) as Record<string, ResMap>)[String(viewer)];
      return mine && handTotal(mine) > 0 ? { text: t("events:settlers_gathered_you", { res: formatRes(t, mine) }), seat: viewer } : null;
    }
    case "robber_moved": return { text: t("events:robber_moved"), seat: null };
    case "robber_stole": {
      const lost = ev.lost as ResMap | undefined;
      return { text: tw("robber_stole", { who, res: lost ? formatRes(t, lost) : "" }), seat };
    }
    case "built": return { text: tw("built", { who, kind: kindName(ev.kind) }), seat };
    case "construction_cancelled": {
      // The refund goes back to the hand: say so, or a robbery right after reads as if it was lost.
      const refund = ev.refund as ResMap | undefined;
      const reason = t(`events:reason.${String(ev.reason)}`);
      return handTotal(refund) > 0
        ? { text: tw("construction_cancelled_refund", { who, reason, res: formatRes(t, refund) }), seat }
        : { text: tw("construction_cancelled", { who, reason }), seat };
    }
    case "setup_complete": return { text: tw("setup_complete", { who }), seat };
    case "starting_resources": {
      const g = ev.gained as ResMap | undefined;
      return handTotal(g) > 0 ? { text: tw("starting_resources", { who, res: formatRes(t, g) }), seat } : null;
    }
    case "traded": return {
      text: tw("traded", { who, give: formatRes(t, ev.give as ResMap), get: formatRes(t, ev.get as ResMap) }), seat,
    };
    case "offer_posted":
      return { text: tw("offer_posted", { who, give: formatRes(t, ev.give as ResMap), get: formatRes(t, ev.get as ResMap) }), seat };
    case "offer_closed": {
      if (ev.reason === "accepted") {
        const by = ev.by === viewer ? t("hud:youObject") : name(ev.by as number);
        return { text: tw("offer_accepted", { who, by, give: formatRes(t, ev.give as ResMap), get: formatRes(t, ev.get as ResMap) }), seat };
      }
      if (ev.reason === "expired") return { text: tw("offer_expired", { who }), seat };
      return null;                                        // withdrawn, or its player left: the board shows it
    }
    case "longest_road": {
      if (ev.seat === ev.previous) return null;          // only the lengths changed
      if (seat === null) return { text: t("events:longest_road_none"), seat: null };
      const length = (ev.lengths as Record<string, number> | undefined)?.[String(seat)] ?? 0;
      return { text: t(seat === viewer ? "events:longest_road_you" : "events:longest_road", { who, count: length }), seat };
    }
    case "dev_card_bought":
      if (seat === viewer && ev.card) return { text: t("events:dev_bought_you", { card: t(`hud:dev.kind.${String(ev.card)}`) }), seat };
      return { text: t("events:dev_bought", { who }), seat };
    case "dev_card_played": {
      const victim = typeof ev.victim === "number" ? (ev.victim === viewer ? t("hud:youObject") : name(ev.victim)) : null;
      switch (ev.card) {
        case "knight":
          return { text: victim ? tw("dev_knight_robbed", { who, victim }) : tw("dev_knight", { who }), seat };
        case "victory_point": return { text: tw("dev_victory_point", { who }), seat };
        case "road_building": return { text: tw("dev_road_building", { who, count: ev.roads ?? 0 }), seat };
        case "year_of_plenty": return { text: tw("dev_year_of_plenty", { who, res: formatRes(t, ev.took as ResMap) }), seat };
        case "monopoly": {
          const total = Object.values((ev.taken ?? {}) as Record<string, number>).reduce((a, n) => a + n, 0);
          return { text: tw("dev_monopoly", { who, res: t(`hud:res.${String(ev.resource)}`), count: total }), seat };
        }
        case "veteran_knight":
        case "elite_knight": {
          const card = t(`hud:dev.kind.${String(ev.card)}`);
          return { text: victim ? tw("dev_strong_knight_robbed", { who, victim, card, count: ev.stolen ?? 0 }) : tw("dev_strong_knight", { who, card }), seat };
        }
        case "fishing_fleet":
        case "merchant":
        case "great_market":
        case "architect":
          return { text: tw("dev_effect", { who, card: t(`hud:dev.kind.${String(ev.card)}`), count: ev.rolls ?? 0 }), seat };
        case "causeway": return { text: tw("dev_causeway", { who, count: ev.roads ?? 0 }), seat };
        case "bountiful_harvest": return { text: tw("dev_harvest", { who, res: formatRes(t, ev.took as ResMap) }), seat };
        case "tribute": {
          const total = Object.values((ev.taken ?? {}) as Record<string, number>).reduce((a, n) => a + n, 0);
          return { text: tw("dev_tribute", { who, count: total }), seat };
        }
        default: return null;
      }
    }
    case "largest_army": {
      if (ev.seat === ev.previous) return null;
      if (seat === null) return { text: t("events:largest_army_none"), seat: null };
      const knights = (ev.knights as Record<string, number> | undefined)?.[String(seat)] ?? 0;
      return { text: t(seat === viewer ? "events:largest_army_you" : "events:largest_army", { who, count: knights }), seat };
    }
    case "age_advance_started": return { text: tw("age_started", { who, age: AGE_ROMAN[Number(ev.age) - 1] ?? ev.age }), seat };
    case "largest_population": {
      if (ev.seat === ev.previous) return null;          // only the populations changed
      if (seat === null) return { text: t("events:largest_population_none"), seat: null };
      const pop = (ev.population as Record<string, number> | undefined)?.[String(seat)] ?? 0;
      return { text: t(seat === viewer ? "events:largest_population_you" : "events:largest_population", { who, count: pop }), seat };
    }
    case "age_reached": return { text: tw("age_reached", { who, age: AGE_ROMAN[Number(ev.age) - 1] ?? ev.age }), seat };
    case "resigned": return { text: t(seat === viewer ? "events:resigned_you" : "events:resigned", { who }), seat };
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

/** Above this many players the score list can fold to the leaders and you. */
export const MANY_PLAYERS = 6;
/** Leaders shown (besides you) while a long score list is folded. */
export const FOLDED_LEADERS = 3;

/** Seats shown in the score list, in seat order: everyone, or (folded) the
 * ``FOLDED_LEADERS`` players with the most points plus your own seat. */
export function visibleScoreSeats(
  players: { seat: number; points?: number }[], mySeat: number | null, folded: boolean,
): number[] {
  const all = players.map((p) => p.seat);
  if (!folded || players.length <= MANY_PLAYERS) return all;
  const leaders = [...players].sort((a, b) => (b.points ?? 0) - (a.points ?? 0) || a.seat - b.seat)
    .slice(0, FOLDED_LEADERS).map((p) => p.seat);
  const keep = new Set(leaders);
  if (mySeat !== null) keep.add(mySeat);
  return all.filter((s) => keep.has(s));
}
