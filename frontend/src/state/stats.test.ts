import { describe, expect, it } from "vitest";

import type { GameStateView } from "../protocol/types";
import { ageMarks, pointsBreakdown, scoreAt, scoreLine, stepPath } from "./stats";
import { applyEvent } from "./store";

function state(): GameStateView {
  return {
    phase: "running", now: 60_000, viewer: 0, bank: {}, robber: null, clock_started: true, next_roll_at: null,
    last_roll: null, dice_history: [], winner: null, finished_at: null, settlers: [], constructions: [], roads: [],
    buildings: [
      { kind: "settlement", seat: 0, vertex: 1 }, { kind: "settlement", seat: 0, vertex: 5 },
      { kind: "city", seat: 0, vertex: 9 }, { kind: "settlement", seat: 1, vertex: 12 },
    ],
    players: [
      { seat: 0, name: "a", colour: "red", pieces: {}, setup: { remaining: {}, done: true, settlements_built: 2 }, settlers: [], points: 7 },
      { seat: 1, name: "b", colour: "blue", pieces: {}, setup: { remaining: {}, done: true, settlements_built: 2 }, settlers: [], points: 1 },
    ],
    longest_road: { holder: 0, lengths: { "0": 6 } },
    dev_cards: { deck_left: 10, army: null, players: {} },
    stats: { timeline: { "0": [[0, 0]], "1": [[0, 0]] }, produced: {} },
  };
}

const settings = { victory: { building_points: { settlement: 1, city: 2, megacity: 3 }, longest_road: { points: 2 } } };

describe("stats", () => {
  it("splits a score by source, the rest being point cards", () => {
    const parts = pointsBreakdown(settings, state(), 0);
    expect(parts).toEqual([
      { source: "settlement", count: 2, points: 2 },
      { source: "city", count: 1, points: 2 },
      { source: "longest_road", count: 1, points: 2 },
      { source: "victory_point", count: 1, points: 1 },
    ]);
    expect(pointsBreakdown(settings, state(), 1)).toEqual([{ source: "settlement", count: 1, points: 1 }]);
  });

  it("copes with ages off (an empty ages object)", () => {
    const s = state();
    s.ages = {};
    expect(pointsBreakdown(settings, s, 1)).toEqual([{ source: "settlement", count: 1, points: 1 }]);
  });

  it("counts the points of the ages reached", () => {
    const s = state();
    s.players[1]!.points = 4;
    s.ages = { players: { "1": { age: 3, advancing: null, reached: { "2": 1000, "3": 2000 } } } };
    const withAges = { ...settings, ages: { age2: { bonus: { points: 1 } }, age3: { bonus: { points: 2 } } } };
    expect(pointsBreakdown(withAges, s, 1)).toEqual([
      { source: "settlement", count: 1, points: 1 }, { source: "ages", count: 2, points: 3 },
    ]);
  });

  it("mirrors score changes and dice production from events", () => {
    const s = state();
    applyEvent(s, { k: "points", at: 1000, seat: 1, points: 2 });
    applyEvent(s, { k: "points", at: 2000, seat: 1, points: 2 });
    applyEvent(s, { k: "produced", at: 3000, roll: 6, gains: { "1": { ore: 2 } } });
    applyEvent(s, { k: "produced", at: 4000, roll: 6, gains: { "1": { ore: 1, wool: 1 } } });
    applyEvent(s, { k: "resigned", at: 5000, seat: 1, returned: {} });
    expect(s.stats!.timeline["1"]).toEqual([[0, 0], [1000, 2]]);
    expect(s.stats!.produced["1"]).toEqual({ ore: 3, wool: 1 });
    expect(s.players[1]!.resigned).toBe(true);
    expect(scoreLine(s, 1, 9000)).toEqual([[0, 0], [1000, 2], [9000, 2]]);
    expect(stepPath([[0, 0], [10, 2]], (t) => t, (p) => -p)).toBe("M0.0,0.0H10.0V-2.0");
  });
});

describe("age marks", () => {
  it("lists the ages reached after the first, oldest first", () => {
    const s = state();
    s.ages = { players: {
      "0": { age: 3, advancing: null, reached: { "3": 50_000, "2": 20_000 } },
      "1": { age: 1, advancing: null, reached: {} },
    } };
    expect(ageMarks(s, 0)).toEqual([[2, 20_000], [3, 50_000]]);
    expect(ageMarks(s, 1)).toEqual([]);
    expect(ageMarks(state(), 0)).toEqual([]);
  });

  it("reads the score of a step line at a time", () => {
    const line: [number, number][] = [[0, 0], [10_000, 2], [30_000, 4]];
    expect(scoreAt(line, 5_000)).toBe(0);
    expect(scoreAt(line, 10_000)).toBe(2);
    expect(scoreAt(line, 99_000)).toBe(4);
  });
});
