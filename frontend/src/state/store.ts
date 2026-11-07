// GameStore: the client's mirror of the server state. Reducers only assign the
// resulting values that events carry; no game rule lives here. No DOM or Pixi
// imports, so a later 3D renderer reuses it unchanged.
import type {
  BoardMsg, BuildKind, ConstructionView, GameEvent, GameStateView, PlayerView, ResMap, ServerMsg, SettlerView,
} from "../protocol/types";

export type Listener = (store: GameStore) => void;

export class GameStore {
  board: BoardMsg | null = null;
  state: GameStateView | null = null;
  seat: number | null = null;
  gameCode = "";
  /** Game settings from the welcome message (JSON as the server sent it). */
  settings: Record<string, unknown> = {};
  /** Last applied ``seq`` of this audience's stream. */
  seq = 0;
  /** Bumps on every change; renderers redraw static layers when it moves. */
  version = 0;
  lastEvents: GameEvent[] = [];
  private listeners = new Set<Listener>();

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Apply one server message. Returns "gap" when an events batch skipped a seq (caller should sync). */
  apply(msg: ServerMsg): "ok" | "gap" | "ignored" {
    switch (msg.t) {
      case "welcome":
        this.seat = msg.seat;
        this.settings = msg.settings;
        this.gameCode = msg.game;
        return this.changed();
      case "board":
        this.board = msg;
        return this.changed();
      case "state":
        this.state = msg.state;
        this.seq = msg.seq;
        this.lastEvents = [];
        return this.changed();
      case "events":
        if (!this.state) return "ignored";
        if (msg.seq <= this.seq) return "ignored";
        if (msg.seq !== this.seq + 1) return "gap";
        this.seq = msg.seq;
        this.state.now = msg.now;
        for (const ev of msg.events) applyEvent(this.state, ev);
        this.lastEvents = msg.events;
        return this.changed();
      default:
        return "ignored";
    }
  }

  player(seat: number): PlayerView | undefined {
    return this.state?.players.find((p) => p.seat === seat);
  }

  colourOf(seat: number): string {
    return this.player(seat)?.colour ?? "grey";
  }

  private changed(): "ok" {
    this.version += 1;
    for (const fn of this.listeners) fn(this);
    return "ok";
  }
}

const num = (v: unknown): number => v as number;

function settler(state: GameStateView, id: number): SettlerView | undefined {
  return state.settlers.find((s) => s.id === id);
}

function setPlayer(state: GameStateView, seat: number, patch: Partial<PlayerView>): void {
  const p = state.players.find((x) => x.seat === seat);
  if (p) Object.assign(p, patch);
}

/** Assign the resulting values one event carries. Unknown kinds are ignored. */
export function applyEvent(state: GameStateView, ev: GameEvent): void {
  switch (ev.k) {
    case "clock_started":
      state.clock_started = true;
      state.next_roll_at = num(ev.next_roll_at);
      break;
    case "dice_rolled":
      state.last_roll = ev.dice as number[];
      state.dice_history = [...state.dice_history, num(ev.sum)];
      state.next_roll_at = ev.next_roll_at as number | null;
      break;
    case "robber_moved":
      state.robber = num(ev.to_hex);
      break;
    case "hand":
      setPlayer(state, num(ev.seat), ev.hand
        ? { hand: ev.hand as ResMap, hand_count: sum(ev.hand as ResMap) }
        : { hand_count: num(ev.hand_count) });
      break;
    case "points":
      setPlayer(state, num(ev.seat), { points: num(ev.points) });
      break;
    case "settler_landed": {
      const s: SettlerView = { id: num(ev.settler), seat: num(ev.seat), vertex: num(ev.vertex), path: [], step: null };
      state.settlers = [...state.settlers.filter((x) => x.id !== s.id), s];
      const p = state.players.find((x) => x.seat === s.seat);
      if (p && !p.settlers.includes(s.id)) p.settlers = [...p.settlers, s.id];
      break;
    }
    case "settler_path": {
      const s = settler(state, num(ev.settler));
      if (s) s.path = ev.path as number[];
      break;
    }
    case "settler_step": {
      const s = settler(state, num(ev.settler));
      if (s) {
        s.step = { edge: num(ev.edge), from_v: num(ev.from_v), to_v: num(ev.to_v), t0: num(ev.t0), t1: num(ev.t1) };
        // The engine pops the next vertex off the path when a step starts but only
        // sends settler_path when the path is (re)planned, so mirror the pop here.
        if (s.path[0] === s.step.to_v) s.path = s.path.slice(1);
      }
      break;
    }
    case "settler_arrived": {
      const s = settler(state, num(ev.settler));
      if (s) {
        s.vertex = num(ev.vertex);
        s.step = null;
      }
      break;
    }
    case "settler_left": {
      const id = num(ev.settler);
      state.settlers = state.settlers.filter((s) => s.id !== id);
      const p = state.players.find((x) => x.seat === num(ev.seat));
      if (p) p.settlers = p.settlers.filter((x) => x !== id);
      break;
    }
    case "construction_started": {
      const c: ConstructionView = {
        id: num(ev.id), seat: num(ev.seat), kind: ev.kind as BuildKind, target: num(ev.target),
        builder: ev.builder as number | null, t0: num(ev.t0), t1: num(ev.t1), paid: (ev.paid ?? {}) as ResMap,
      };
      state.constructions = [...state.constructions.filter((x) => x.id !== c.id), c];
      break;
    }
    case "construction_cancelled": {
      const id = num(ev.id);
      state.constructions = state.constructions.filter((c) => c.id !== id);
      break;
    }
    case "built": {
      const kind = ev.kind as BuildKind;
      const seat = num(ev.seat);
      const target = num(ev.target);
      state.constructions = state.constructions.filter((c) => !(c.target === target && c.kind === kind && c.seat === seat));
      if (kind === "road") state.roads = [...state.roads, { edge: target, seat }];
      else state.buildings = [...state.buildings.filter((b) => b.vertex !== target), { kind, seat, vertex: target }];
      setPlayer(state, seat, { points: num(ev.points_after) });
      break;
    }
    case "setup_complete": {
      const p = state.players.find((x) => x.seat === num(ev.seat));
      if (p) p.setup = { ...p.setup, done: true };
      break;
    }
    case "buildable":
      if (state.viewer === num(ev.seat)) {
        state.buildable = {
          roads: ev.roads as number[], settlements: ev.settlements as number[],
          cities: ev.cities as number[], megacities: (ev.megacities as number[] | undefined) ?? [],
        };
      }
      break;
    case "game_over":
      state.phase = "finished";
      state.winner = ev.winner as number | null;
      state.finished_at = (ev.at as number | undefined) ?? state.now;
      for (const [seat, pts] of Object.entries(ev.points as Record<string, number>)) {
        setPlayer(state, Number(seat), { points: pts });
      }
      break;
    default:
      break;
  }
  if (state.phase === "setup" && state.clock_started) state.phase = "running";
}

function sum(m: ResMap): number {
  return Object.values(m).reduce((a, b) => a + (b ?? 0), 0);
}
