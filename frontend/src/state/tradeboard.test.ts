import { describe, expect, it } from "vitest";

import type { GameStateView, TradeOffer } from "../protocol/types";
import { applyEvent } from "./store";
import { compact, othersOffers, whyNotAccept, whyNotPost } from "./tradeboard";

const player = (seat: number, hand: Record<string, number> | undefined, done = true) =>
  ({ seat, hand, hand_count: 0, setup: { remaining: {}, done, settlements_built: 2 } });

const state = (offers: TradeOffer[] = []) => ({
  viewer: 0,
  players: [player(0, { brick: 2, ore: 0 }), player(1, undefined), player(2, { wool: 1 }, false)],
  trade_board: { offers },
}) as unknown as GameStateView;

const offer = (id: number, seat: number, give: Record<string, number>, get: Record<string, number>): TradeOffer =>
  ({ id, seat, give, get, at: 0, expires_at: null });

describe("trade board on the client", () => {
  it("checks an offer before posting it", () => {
    const s = state();
    expect(whyNotPost(s, 0, {}, { brick: 2 }, { ore: 1 })).toBeNull();
    expect(whyNotPost(s, 0, {}, { brick: 3 }, { ore: 1 })).toBe("offer.cannot_afford");
    expect(whyNotPost(s, 0, {}, { brick: 0 }, { ore: 1 })).toBe("offer.empty");
    expect(whyNotPost(s, 0, {}, { brick: 1 }, { brick: 1 })).toBe("offer.same_resource");
    expect(whyNotPost(s, 0, { trading: { player_trades: false } }, { brick: 1 }, { ore: 1 })).toBe("offer.disabled");
    expect(whyNotPost(s, 2, {}, { wool: 1 }, { ore: 1 })).toBe("offer.setup_not_done");
    const full = state([offer(0, 0, { brick: 1 }, { ore: 1 })]);
    expect(whyNotPost(full, 0, { trading: { max_open_offers: 1 } }, { brick: 1 }, { ore: 1 })).toBe("offer.too_many");
  });

  it("checks an offer before accepting it", () => {
    const s = state();
    expect(whyNotAccept(s, 0, offer(1, 1, { wool: 1 }, { brick: 2 }))).toBeNull();      // poster's hand hidden
    expect(whyNotAccept(s, 0, offer(1, 1, { wool: 1 }, { ore: 1 }))).toBe("offer.cannot_afford");
    expect(whyNotAccept(s, 0, offer(1, 0, { brick: 1 }, { ore: 1 }))).toBe("offer.own");
    expect(whyNotAccept(s, 1, offer(1, 0, { brick: 3 }, { ore: 1 }))).toBe("offer.poster_short");
    expect(othersOffers(state([offer(0, 0, {}, {}), offer(1, 1, {}, {})]), 0).map((o) => o.id)).toEqual([1]);
    expect(compact({ brick: 0, ore: 2 })).toEqual({ ore: 2 });
  });

  it("keeps the board in step with the events", () => {
    const s = state();
    applyEvent(s, { k: "offer_posted", at: 5, offer: 3, seat: 1, give: { wool: 1 }, get: { ore: 1 }, expires_at: null });
    applyEvent(s, { k: "offer_posted", at: 6, offer: 4, seat: 0, give: { brick: 1 }, get: { ore: 1 }, expires_at: 99 });
    expect(s.trade_board!.offers.map((o) => o.id)).toEqual([3, 4]);
    applyEvent(s, { k: "offer_closed", at: 7, offer: 3, seat: 1, reason: "accepted", by: 0 });
    expect(s.trade_board!.offers.map((o) => [o.id, o.expires_at])).toEqual([[4, 99]]);
  });
});
