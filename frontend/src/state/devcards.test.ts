import { describe, expect, it } from "vitest";

import type { BoardMsg, DevCardsPlayer, GameStateView } from "../protocol/types";
import { knightHexes, knightVictims, whyNot } from "./devcards";

const hex = (id: number, q: number, r: number, terrain: string | null = "forest", land = true) =>
  ({ id, q, r, land, terrain, token: 5 }) as BoardMsg["hexes"][number];

const board = {
  t: "board",
  hexes: [hex(0, 0, 0, "desert"), hex(1, 1, 0), hex(2, 2, 0), hex(3, 3, 0), hex(4, 4, 0), hex(5, -1, 0, null, false)],
  vertices: [
    { id: 0, q: 1, r: 0, c: "N", hexes: [1], adj_v: [], adj_e: [] },
    { id: 1, q: 1, r: 0, c: "S", hexes: [1, 2], adj_v: [], adj_e: [] },
  ],
  edges: [], fishing: [], harbors: [], robber_start: 0,
} as unknown as BoardMsg;

const state = (over: Partial<GameStateView> = {}) => ({
  robber: 0, dice_history: [8, 9], buildings: [], ...over,
}) as unknown as GameStateView;

describe("development card rules on the client", () => {
  it("plays a card bought before the latest roll, once per roll", () => {
    const me: DevCardsPlayer = { knights: 0, last_play: null };
    const s = state();
    expect(whyNot({ kind: "knight", at: 0, roll: 1 }, me, s, {}, 0)).toBeNull();
    expect(whyNot({ kind: "knight", at: 0, roll: 2 }, me, s, {}, 0)).toBe("dev.too_new");
    expect(whyNot({ kind: "knight", at: 0, roll: 0 }, { ...me, last_play: { at: 0, roll: 2 } }, s, {}, 0)).toBe("dev.cooldown");
    const ms = { dev_cards: { cooldown: "ms", cooldown_ms: 1000 } };
    expect(whyNot({ kind: "monopoly", at: 500, roll: 0 }, me, s, ms, 1400)).toBe("dev.too_new");
    expect(whyNot({ kind: "monopoly", at: 500, roll: 0 }, me, s, ms, 1500)).toBeNull();
    expect(whyNot({ kind: "victory_point", at: 0, roll: 0 }, me, s, { dev_cards: { vp_cards_must_be_played: false } }, 0))
      .toBe("dev.not_playable");
  });

  it("finds the knight's hexes and whom it can rob", () => {
    expect(knightHexes(board, state(), {})).toEqual([1, 2, 3]);
    expect(knightHexes(board, state(), { robber: { knight_max_distance: 1 } })).toEqual([1]);
    expect(knightHexes(board, state({ robber: 1 }), { robber: { may_enter_desert: false, knight_max_distance: 1 } })).toEqual([2]);
    const s = state({ buildings: [{ vertex: 0, seat: 1, kind: "settlement" }, { vertex: 1, seat: 0, kind: "city" }] });
    expect(knightVictims(board, s, 1, 0)).toEqual([1]);
    expect(knightVictims(board, s, 2, 1)).toEqual([0]);
  });
});
