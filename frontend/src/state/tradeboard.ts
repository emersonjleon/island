// Trade board helpers for the HUD. They mirror the engine (engine/rules/trade_board.py)
// so the client can grey out what the server would refuse; the server still decides.
import type { GameStateView, ResMap, Resource, TradeOffer } from "../protocol/types";

interface TradingSettings { player_trades?: boolean; max_open_offers?: number }

function trading(settings: Record<string, unknown>): TradingSettings {
  return (settings["trading"] as TradingSettings | undefined) ?? {};
}

export function playerTradesOn(settings: Record<string, unknown>): boolean {
  return trading(settings).player_trades !== false;
}

export function offersOf(state: GameStateView | null): TradeOffer[] {
  return state?.trade_board?.offers ?? [];
}

/** Open offers from other players (what the Trade button counts). */
export function othersOffers(state: GameStateView | null, seat: number | null): TradeOffer[] {
  return offersOf(state).filter((o) => o.seat !== seat);
}

function hasCards(hand: ResMap | undefined, need: ResMap): boolean {
  return Object.entries(need).every(([r, n]) => (hand?.[r as Resource] ?? 0) >= (n ?? 0));
}

function nonEmpty(m: ResMap): boolean {
  return Object.values(m).some((n) => (n ?? 0) > 0);
}

/** Drop zero entries, so the intent names only what changes hands. */
export function compact(m: ResMap): ResMap {
  return Object.fromEntries(Object.entries(m).filter(([, n]) => (n ?? 0) > 0)) as ResMap;
}

/** Why the player can't post this offer (an error code), or null. */
export function whyNotPost(state: GameStateView, seat: number, settings: Record<string, unknown>,
  give: ResMap, get: ResMap): string | null {
  const me = state.players.find((p) => p.seat === seat);
  if (!playerTradesOn(settings)) return "offer.disabled";
  if (!me?.setup.done) return "offer.setup_not_done";
  if (!nonEmpty(give) || !nonEmpty(get)) return "offer.empty";
  if (Object.keys(compact(give)).some((r) => (get[r as Resource] ?? 0) > 0)) return "offer.same_resource";
  const max = trading(settings).max_open_offers ?? 3;
  if (offersOf(state).filter((o) => o.seat === seat).length >= max) return "offer.too_many";
  if (me.hand && !hasCards(me.hand, give)) return "offer.cannot_afford";
  return null;
}

/** Why the player can't accept ``offer`` (an error code), or null. The poster's hand is
 * checked only when it is visible (open hands); otherwise the server says. */
export function whyNotAccept(state: GameStateView, seat: number, offer: TradeOffer): string | null {
  const me = state.players.find((p) => p.seat === seat);
  if (offer.seat === seat) return "offer.own";
  if (!me?.setup.done) return "offer.setup_not_done";
  if (me.hand && !hasCards(me.hand, offer.get)) return "offer.cannot_afford";
  const poster = state.players.find((p) => p.seat === offer.seat);
  if (poster?.hand && !hasCards(poster.hand, offer.give)) return "offer.poster_short";
  return null;
}
