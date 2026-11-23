// Development card helpers for the HUD and the controls. They mirror the engine
// (engine/rules/devcards.py) so the client can grey out what the server would refuse;
// the server still decides.
import type { BoardMsg, DevCard, DevCardKind, DevCardsPlayer, GameStateView } from "../protocol/types";

export const DEV_KINDS: DevCardKind[] = ["knight", "victory_point", "road_building", "year_of_plenty", "monopoly"];

interface DevSettings {
  cooldown?: "per_roll" | "ms";
  cooldown_ms?: number | null;
  vp_cards_must_be_played?: boolean;
  year_of_plenty_cards?: number;
}
interface RobberSettings {
  enabled?: boolean; knight_max_distance?: number; may_enter_desert?: boolean; may_enter_fishing?: boolean;
  spare_setup?: boolean; spare_setup_ms?: number | null; friendly_min_points?: number;
}

function devSettings(settings: Record<string, unknown>): DevSettings {
  return (settings["dev_cards"] as DevSettings | undefined) ?? {};
}

export function devPlayer(state: GameStateView | null, seat: number | null): DevCardsPlayer | undefined {
  if (!state || seat === null) return undefined;
  return state.dev_cards?.players[String(seat)];
}

export function plentyCount(settings: Record<string, unknown>): number {
  return devSettings(settings).year_of_plenty_cards ?? 2;
}

/** Why a card can't be played now (an error code the HUD translates), or null when it can. */
export function whyNot(card: DevCard, me: DevCardsPlayer, state: GameStateView,
  settings: Record<string, unknown>, now: number): string | null {
  const cfg = devSettings(settings);
  if (card.kind === "victory_point" && cfg.vp_cards_must_be_played === false) return "dev.not_playable";
  if (card.kind === "knight" && (settings["robber"] as RobberSettings | undefined)?.enabled === false) return "dev.no_robber";
  const rolls = state.dice_history.length;
  if (cfg.cooldown === "ms") {
    const wait = cfg.cooldown_ms ?? 0;
    if ((card.at ?? 0) + wait > now) return "dev.too_new";
    if (me.last_play && me.last_play.at + wait > now) return "dev.cooldown";
    return null;
  }
  if ((card.roll ?? 0) >= rolls) return "dev.too_new";
  if (me.last_play && me.last_play.roll >= rolls) return "dev.cooldown";
  return null;
}

function hexDistance(a: { q: number; r: number }, b: { q: number; r: number }): number {
  const dq = a.q - b.q;
  const dr = a.r - b.r;
  return (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2;
}

/** Hexes a knight may send the robber to (engine: devcards._knight_target). */
export function knightHexes(board: BoardMsg, state: GameStateView, settings: Record<string, unknown>): number[] {
  const rs = (settings["robber"] as RobberSettings | undefined) ?? {};
  if (rs.enabled === false || state.robber === null) return [];
  const start = board.hexes[state.robber];
  if (!start) return [];
  const max = rs.knight_max_distance ?? 3;
  const fishing = new Set(rs.may_enter_fishing ? board.fishing.map((f) => f.hex) : []);
  return board.hexes.filter((h) => h && (h.land || fishing.has(h.id)) && h.id !== start.id && hexDistance(h, start) <= max
    && (h.terrain !== "desert" || rs.may_enter_desert !== false)).map((h) => h.id);
}

/** Other players with a building on ``hex`` (whom a knight there could rob), seat order.
 * Players still in setup are left out while ``robber.spare_setup`` is on (the default), during the
 * first ``robber.spare_setup_ms`` of the game, and players with fewer than
 * ``robber.friendly_min_points`` points (friendly robber). */
export function knightVictims(board: BoardMsg, state: GameStateView, hex: number, seat: number,
  settings: Record<string, unknown> = {}): number[] {
  const rs = (settings["robber"] as RobberSettings | undefined) ?? {};
  const limit = rs.spare_setup_ms === undefined ? 300000 : rs.spare_setup_ms;
  const spare = rs.spare_setup !== false && (limit === null || (state.now ?? 0) < limit);
  const friendly = rs.friendly_min_points ?? 0;
  const inSetup = new Set((state.players ?? []).filter((p) => (spare && !p.setup?.done)
    || (friendly > 0 && (p.points ?? 0) < friendly)).map((p) => p.seat));
  const corners = new Set(board.vertices.filter((v) => v.hexes.includes(hex)).map((v) => v.id));
  const seats = new Set(state.buildings.filter((b) => corners.has(b.vertex) && b.seat !== seat
    && !inSetup.has(b.seat)).map((b) => b.seat));
  return [...seats].sort((a, b) => a - b);
}

/** Cards in a player's hand that others can count (own cards, or the count shown). */
export function cardCount(p: DevCardsPlayer | undefined): number {
  return p?.cards?.length ?? p?.count ?? 0;
}
