// Site-wide chat model: the public room, private conversations, friends and the
// privacy setting, as the /ws/social/ socket reports them (see chat/consumers.py
// SocialConsumer). No DOM here, so it is tested on its own.
import { ChatLog, type ChatLine } from "./model";

export type Privacy = "everyone" | "friends" | "games";
export const PRIVACY: Privacy[] = ["everyone", "friends", "games"];

export interface Person { id: number; name: string }

/** One message as the server sends it (chat/social.py ``to_wire``). */
export interface SocialMessage {
  id: number;
  from: number;
  name: string;
  /** Recipient's id; null for the public room. */
  to: number | null;
  to_name: string | null;
  text: string;
  at: number;
}

export interface SocialState {
  me: Person;
  privacy: Privacy;
  friends: Person[];
  incoming: Person[];
  outgoing: Person[];
}

export type SocialFrame =
  | ({ t: "social" } & SocialState)
  | { t: "public" | "dm"; msgs: SocialMessage[]; history: boolean }
  | { t: "notice"; code: string; params: Record<string, unknown> }
  | { t: "pong" };

function isPerson(v: unknown): v is Person {
  const o = v as Partial<Person> | null;
  return !!o && typeof o.id === "number" && typeof o.name === "string";
}

function people(v: unknown): Person[] {
  return Array.isArray(v) ? v.filter(isPerson).map(({ id, name }) => ({ id, name })) : [];
}

function isMessage(v: unknown): v is SocialMessage {
  const o = v as Partial<SocialMessage> | null;
  return !!o && typeof o.id === "number" && typeof o.from === "number" && typeof o.name === "string"
    && typeof o.text === "string" && (o.to === null || typeof o.to === "number");
}

export function parseSocialFrame(data: unknown): SocialFrame | null {
  const o = data as Record<string, unknown> | null;
  if (!o || typeof o !== "object") return null;
  if (o.t === "pong") return { t: "pong" };
  if (o.t === "social" && isPerson(o.me) && PRIVACY.includes(o.privacy as Privacy)) {
    return {
      t: "social", me: { id: o.me.id, name: o.me.name }, privacy: o.privacy as Privacy,
      friends: people(o.friends), incoming: people(o.incoming), outgoing: people(o.outgoing),
    };
  }
  if ((o.t === "public" || o.t === "dm") && Array.isArray(o.msgs)) {
    return {
      t: o.t, history: o.history === true,
      msgs: o.msgs.filter(isMessage).map((m) => ({
        ...m, to_name: typeof m.to_name === "string" ? m.to_name : null, at: typeof m.at === "number" ? m.at : 0,
      })),
    };
  }
  if (o.t === "notice" && typeof o.code === "string") {
    const params = o.params && typeof o.params === "object" ? (o.params as Record<string, unknown>) : {};
    return { t: "notice", code: o.code, params };
  }
  return null;
}

/** A social message in the shape the shared chat view shows. */
export function toLine(m: SocialMessage): ChatLine {
  return { id: m.id, uid: m.from, name: m.name, colour: "", seat: null, player: true, text: m.text, at: m.at };
}

export interface Conversation { with: Person; log: ChatLog; last: number }

export type SocialListener = (store: SocialStore) => void;

/** Everything the social panel shows, kept up to date from the socket's frames. */
export class SocialStore {
  state: SocialState | null = null;
  readonly publicLog = new ChatLog();
  /** Private conversations by the other person's id. */
  readonly conversations = new Map<number, Conversation>();
  /** The last refusal from the server (a "chat.*" code) outside any one conversation. */
  error: { code: string; params: Record<string, unknown> } | null = null;
  private listeners = new Set<SocialListener>();
  /** Messages received before the first state frame told us who "me" is. */
  private pendingDms: SocialFrame[] = [];

  subscribe(fn: SocialListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private changed(): void {
    for (const fn of this.listeners) fn(this);
  }

  receive(frame: SocialFrame): void {
    if (frame.t === "social") {
      this.state = { me: frame.me, privacy: frame.privacy, friends: frame.friends, incoming: frame.incoming, outgoing: frame.outgoing };
      const waiting = this.pendingDms;
      this.pendingDms = [];
      for (const f of waiting) this.receive(f);
    } else if (frame.t === "public") {
      if (!frame.history) this.error = null;
      this.publicLog.receive({ t: "chat", msgs: frame.msgs.map(toLine), history: frame.history });
    } else if (frame.t === "dm") {
      if (!this.state) {
        this.pendingDms.push(frame);
        return;
      }
      if (!frame.history) this.error = null;
      this.receiveDms(frame.msgs, frame.history);
    } else if (frame.t === "notice") {
      this.refused(frame.code, frame.params);
      return;
    } else {
      return;
    }
    this.changed();
  }

  private receiveDms(msgs: SocialMessage[], history: boolean): void {
    const me = this.state!.me.id;
    const byOther = new Map<number, SocialMessage[]>();
    for (const m of msgs) {
      const other = m.from === me ? m.to! : m.from;
      const name = m.from === me ? (m.to_name ?? "?") : m.name;
      const convo = this.conversation({ id: other, name });
      convo.last = Math.max(convo.last, m.id);
      byOther.set(other, [...(byOther.get(other) ?? []), m]);
    }
    for (const [other, list] of byOther) {
      this.conversations.get(other)!.log.receive({ t: "chat", msgs: list.map(toLine), history });
    }
  }

  /** The conversation with someone, started empty if there is none yet. */
  conversation(person: Person): Conversation {
    let convo = this.conversations.get(person.id);
    if (!convo) {
      convo = { with: { ...person }, log: new ChatLog(), last: 0 };
      this.conversations.set(person.id, convo);
    }
    return convo;
  }

  /** Conversations, the latest message first. */
  sortedConversations(): Conversation[] {
    return [...this.conversations.values()].sort((a, b) => b.last - a.last || a.with.name.localeCompare(b.with.name));
  }

  refused(code: string, params: Record<string, unknown> = {}): void {
    this.error = { code, params };
    this.changed();
  }

  clearError(): void {
    if (!this.error) return;
    this.error = null;
    this.changed();
  }

  /** Unread private messages plus friend requests waiting for an answer: the number on the button. */
  attention(): number {
    let n = this.state?.incoming.length ?? 0;
    for (const c of this.conversations.values()) n += c.log.unread;
    return n;
  }

  isFriend(id: number): boolean {
    return !!this.state?.friends.some((f) => f.id === id);
  }

  /** Whether a friend request to this person (or from them) is already waiting. */
  isPending(id: number): boolean {
    return !!this.state && [...this.state.incoming, ...this.state.outgoing].some((p) => p.id === id);
  }
}
