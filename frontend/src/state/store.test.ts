import { describe, expect, it } from "vitest";

import type { BoardMsg, EventsMsg, GameStateView, StateMsg } from "../protocol/types";
import { fixture } from "../testing/fixtures";
import { GameStore, applyEvent } from "./store";

function baseState(): GameStateView {
  return {
    phase: "setup", now: 0, viewer: 0, bank: {}, buildings: [], roads: [], settlers: [], constructions: [],
    robber: 9, clock_started: false, next_roll_at: null, last_roll: null, dice_history: [], winner: null,
    finished_at: null,
    players: [0, 1].map((seat) => ({ seat, name: `p${seat}`, colour: seat ? "blue" : "red", pieces: {},
      setup: { remaining: {}, done: false, settlements_built: 0 }, settlers: [] })),
  };
}

describe("GameStore contract with the Python fixtures", () => {
  it("loads board and state fixtures", () => {
    const store = new GameStore();
    expect(store.apply(fixture<BoardMsg>("board.json"))).toBe("ok");
    expect(store.apply({ ...fixture<StateMsg>("state_seat0.json"), t: "state" })).toBe("ok");
    expect(store.board!.hexes.length).toBeGreaterThan(19);
    expect(store.state!.players[0]!.hand).toBeDefined();
    expect(store.state!.players[1]!.hand).toBeUndefined();
  });

  it("applies every fixture event kind without throwing", () => {
    for (const name of ["events_seat0.json", "events_seat1.json", "events_spectator.json"]) {
      const msg = fixture<EventsMsg>(name);
      const state = baseState();
      for (const ev of msg.events) applyEvent(state, ev);
      expect(state.phase).toBe("finished");
      expect(state.winner).toBe(2);
    }
  });
});

describe("GameStore reducers", () => {
  function storeWithState(): GameStore {
    const store = new GameStore();
    store.apply({ t: "state", seq: 3, now: 0, state: baseState() });
    return store;
  }

  it("detects gaps and ignores old batches", () => {
    const store = storeWithState();
    expect(store.apply({ t: "events", seq: 3, now: 1, events: [] })).toBe("ignored");
    expect(store.apply({ t: "events", seq: 5, now: 1, events: [] })).toBe("gap");
    expect(store.apply({ t: "events", seq: 4, now: 1, events: [] })).toBe("ok");
    expect(store.seq).toBe(4);
  });

  it("walks a settler, builds and scores", () => {
    const store = storeWithState();
    store.apply({ t: "events", seq: 4, now: 10, events: [
      { k: "settler_landed", settler: 1, seat: 0, vertex: 5 },
      { k: "settler_step", settler: 1, edge: 7, from_v: 5, to_v: 6, t0: 0, t1: 1500 },
      { k: "settler_path", settler: 1, path: [8] },
    ] });
    const s = store.state!;
    expect(s.settlers[0]!.step!.to_v).toBe(6);
    expect(s.players[0]!.settlers).toEqual([1]);
    store.apply({ t: "events", seq: 5, now: 1500, events: [
      { k: "settler_arrived", settler: 1, vertex: 6 },
      { k: "construction_started", id: 3, seat: 0, kind: "settlement", target: 6, builder: 1, t0: 1500, t1: 9500, paid: {} },
    ] });
    expect(s.settlers[0]!.vertex).toBe(6);
    expect(s.constructions).toHaveLength(1);
    store.apply({ t: "events", seq: 6, now: 9500, events: [
      { k: "built", seat: 0, kind: "settlement", target: 6, points_after: 1 },
      { k: "built", seat: 0, kind: "road", target: 7, points_after: 1 },
      { k: "settler_left", settler: 1, seat: 0 },
    ] });
    expect(s.constructions).toHaveLength(0);
    expect(s.buildings).toEqual([{ kind: "settlement", seat: 0, vertex: 6 }]);
    expect(s.roads).toEqual([{ edge: 7, seat: 0 }]);
    expect(s.settlers).toHaveLength(0);
    expect(s.players[0]!.points).toBe(1);
  });

  it("upgrades a settlement in place and tracks the dice clock", () => {
    const store = storeWithState();
    const s = store.state!;
    s.buildings = [{ kind: "settlement", seat: 1, vertex: 4 }];
    store.apply({ t: "events", seq: 4, now: 0, events: [
      { k: "clock_started", next_roll_at: 20000 },
      { k: "dice_rolled", dice: [3, 4], sum: 7, next_roll_at: 40000 },
      { k: "robber_moved", from_hex: 9, to_hex: 2 },
      { k: "built", seat: 1, kind: "city", target: 4, points_after: 2 },
      { k: "hand", seat: 1, hand_count: 3 },
    ] });
    expect(s.phase).toBe("running");
    expect(s.buildings).toEqual([{ kind: "city", seat: 1, vertex: 4 }]);
    expect(s.dice_history).toEqual([7]);
    expect(s.next_roll_at).toBe(40000);
    expect(s.robber).toBe(2);
    expect(s.players[1]!.hand_count).toBe(3);
  });

  it("keeps buildable only for the viewer", () => {
    const store = storeWithState();
    store.apply({ t: "events", seq: 4, now: 0, events: [
      { k: "buildable", seat: 1, roads: [1], settlements: [], cities: [] },
    ] });
    expect(store.state!.buildable).toBeUndefined();
    store.apply({ t: "events", seq: 5, now: 0, events: [
      { k: "buildable", seat: 0, roads: [1], settlements: [2], cities: [] },
    ] });
    expect(store.state!.buildable!.settlements).toEqual([2]);
  });

  it("counts down setup slots as setup pieces are built", () => {
    const state = baseState();
    state.players[0]!.setup = { remaining: { settlement: 2, road: 2 }, done: false, settlements_built: 0 };
    applyEvent(state, { k: "built", seat: 0, kind: "settlement", target: 5, points_after: 1 });
    applyEvent(state, { k: "built", seat: 0, kind: "road", target: 9, points_after: 1 });
    expect(state.players[0]!.setup).toEqual({ remaining: { settlement: 1, road: 1 }, done: false, settlements_built: 1 });
    applyEvent(state, { k: "setup_complete", seat: 0 });
    applyEvent(state, { k: "built", seat: 0, kind: "road", target: 10, points_after: 1 });
    expect(state.players[0]!.setup.remaining.road).toBe(1);
  });
});
