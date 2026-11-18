// Site-wide chat model: the public room, private conversations, friends and the
// privacy setting, as the /ws/social/ socket reports them (see chat/consumers.py
// SocialConsumer). No DOM here, so it is tested on its own.
//
// Private conversations arrive as a list (who, last line, unread count); each one's
// lines are fetched a page at a time when it is opened, and reading one tells the
// server, so unread counts follow the person to every tab and device.
import { ChatLog, type ChatLine } from "./model";

export type Privacy = "everyone" | "friends" | "games";
export const PRIVACY: Privacy[] = ["everyone", "friends", "games"];

export interface Person { id: number; name: string }

/** One message as the server sends it (chat/social.py ``to_wire``). */
export interface SocialMessage {
  id: number;
  /** Writer's user id (null when that account is gone). */
  from: number | null;
  name: string;
  text: string;
  at: number;
}

export interface ConversationSummary { with: Person; last: SocialMessage; unread: number }

export interface SocialState {
  me: Person;
  privacy: Privacy;
  /** Language of the public room you are in, and the rooms there are. */
  room: string;
  rooms: string[];
  friends: Person[];
  incoming: Person[];
  outgoing: Person[];
  conversations: ConversationSummary[];
}

export type SocialFrame =
  | ({ t: "social" } & SocialState)
  | { t: "public"; room: string; msgs: SocialMessage[]; history: boolean; more: boolean }
  | { t: "dm"; with: Person; msgs: SocialMessage[]; history: boolean; more: boolean }
  | { t: "read"; with: number; upto: number }
  | { t: "notice"; code: string; params: Record<string, unknown> }
  | { t: "pong" };

export type SocialSend = (frame: object) => boolean;

function isPerson(v: unknown): v is Person {
  const o = v as Partial<Person> | null;
  return !!o && typeof o.id === "number" && typeof o.name === "string";
}

function person(v: Person): Person {
  return { id: v.id, name: v.name };
}

function people(v: unknown): Person[] {
  return Array.isArray(v) ? v.filter(isPerson).map(person) : [];
}

function isMessage(v: unknown): v is SocialMessage {
  const o = v as Partial<SocialMessage> | null;
  return !!o && typeof o.id === "number" && (o.from === null || typeof o.from === "number")
    && typeof o.name === "string" && typeof o.text === "string";
}

function message(m: SocialMessage): SocialMessage {
  return { id: m.id, from: m.from, name: m.name, text: m.text, at: typeof m.at === "number" ? m.at : 0 };
}

function messages(v: unknown): SocialMessage[] {
  return Array.isArray(v) ? v.filter(isMessage).map(message) : [];
}

function summaries(v: unknown): ConversationSummary[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((c: Partial<ConversationSummary> | null) => (
    c && isPerson(c.with) && isMessage(c.last)
      ? [{ with: person(c.with), last: message(c.last), unread: typeof c.unread === "number" ? c.unread : 0 }]
      : []
  ));
}

export function parseSocialFrame(data: unknown): SocialFrame | null {
  const o = data as Record<string, unknown> | null;
  if (!o || typeof o !== "object") return null;
  if (o.t === "pong") return { t: "pong" };
  if (o.t === "social" && isPerson(o.me) && PRIVACY.includes(o.privacy as Privacy)) {
    const rooms = Array.isArray(o.rooms) ? o.rooms.filter((r): r is string => typeof r === "string") : [];
    return {
      t: "social", me: person(o.me), privacy: o.privacy as Privacy,
      room: typeof o.room === "string" ? o.room : "", rooms,
      friends: people(o.friends), incoming: people(o.incoming), outgoing: people(o.outgoing),
      conversations: summaries(o.conversations),
    };
  }
  if (o.t === "public" && typeof o.room === "string" && Array.isArray(o.msgs)) {
    return { t: "public", room: o.room, msgs: messages(o.msgs), history: o.history === true, more: o.more === true };
  }
  if (o.t === "dm" && isPerson(o.with) && Array.isArray(o.msgs)) {
    return { t: "dm", with: person(o.with), msgs: messages(o.msgs), history: o.history === true, more: o.more === true };
  }
  if (o.t === "read" && typeof o.with === "number" && typeof o.upto === "number") {
    return { t: "read", with: o.with, upto: o.upto };
  }
  if (o.t === "notice" && typeof o.code === "string") {
    const params = o.params && typeof o.params === "object" ? (o.params as Record<string, unknown>) : {};
    return { t: "notice", code: o.code, params };
  }
  return null;
}

/** A social message in the shape the shared chat view shows. */
export function toLine(m: SocialMessage): ChatLine {
  return { id: m.id, uid: m.from ?? undefined, name: m.name, colour: "", seat: null, player: true, text: m.text, at: m.at };
}

/** Lines a conversation or the public room keeps in memory while older pages are loaded. */
const KEEP_LINES = 1000;

/** Lines of a channel that are fetched a page at a time, oldest pages on request. */
export interface Paged {
  log: ChatLog;
  /** The first page has arrived. */
  loaded: boolean;
  /** Older lines exist on the server. */
  more: boolean;
  /** A page was asked for and has not arrived yet. */
  loading: boolean;
}

export interface Conversation extends Paged {
  with: Person;
  /** Newest line seen (for the list order and preview). */
  last: SocialMessage | null;
  unread: number;
}

function paged(): Paged {
  return { log: new ChatLog(KEEP_LINES), loaded: false, more: false, loading: false };
}

export type SocialListener = (store: SocialStore) => void;

/** Everything the social panel shows, kept up to date from the socket's frames. */
export class SocialStore {
  state: SocialState | null = null;
  publicRoom: Paged & { room: string } = { ...paged(), room: "" };
  /** Private conversations by the other person's id. */
  readonly conversations = new Map<number, Conversation>();
  /** The last refusal from the server (a "chat.*" code), until the next line arrives. */
  error: { code: string; params: Record<string, unknown> } | null = null;
  /** The conversation on screen, whose new lines are read as they come. */
  active: number | null = null;
  private listeners = new Set<SocialListener>();

  constructor(private readonly send: SocialSend = () => false) {}

  get publicLog(): ChatLog {
    return this.publicRoom.log;
  }

  subscribe(fn: SocialListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private changed(): void {
    for (const fn of this.listeners) fn(this);
  }

  receive(frame: SocialFrame): void {
    switch (frame.t) {
      case "social":
        this.receiveState(frame);
        break;
      case "public":
        this.receivePublic(frame);
        break;
      case "dm":
        this.receiveDm(frame);
        break;
      case "read": {
        const convo = this.conversations.get(frame.with);
        if (convo && convo.last && convo.last.id <= frame.upto) convo.unread = 0;
        break;
      }
      case "notice":
        this.error = { code: frame.code, params: frame.params };
        break;
      default:
        return;
    }
    this.changed();
  }

  private receiveState(frame: SocialState): void {
    const { conversations, ...rest } = frame;
    this.state = { ...rest, conversations };
    for (const s of conversations) {
      const convo = this.conversation(s.with);
      convo.with = s.with;
      if (!convo.last || s.last.id >= convo.last.id) {
        convo.last = s.last;
        convo.unread = this.active === s.with.id ? 0 : s.unread;
      }
    }
    if (this.publicRoom.room && this.publicRoom.room !== frame.room) this.publicRoom = { ...paged(), room: frame.room };
    if (this.active !== null) this.readActive();
  }

  private receivePublic(frame: { room: string; msgs: SocialMessage[]; history: boolean; more: boolean }): void {
    if (frame.room !== this.publicRoom.room) {
      if (!frame.history) return;  // a line from the room just left
      this.publicRoom = { ...paged(), room: frame.room };
    }
    const room = this.publicRoom;
    if (frame.history) {
      if (!room.loaded || frame.msgs.length === 0 || frame.msgs[0]!.id < (room.log.lines[0]?.id ?? Infinity)) room.more = frame.more;
      room.loaded = true;
      room.loading = false;
    } else {
      this.error = null;
    }
    room.log.receive({ t: "chat", msgs: frame.msgs.map(toLine), history: frame.history });
  }

  private receiveDm(frame: { with: Person; msgs: SocialMessage[]; history: boolean; more: boolean }): void {
    const convo = this.conversation(frame.with);
    convo.with = frame.with;
    const newest = frame.msgs[frame.msgs.length - 1];
    if (newest && (!convo.last || newest.id > convo.last.id)) convo.last = newest;
    if (frame.history) {
      const oldest = convo.log.lines[0]?.id ?? Infinity;
      if (!convo.loaded || (frame.msgs[0] && frame.msgs[0].id < oldest)) convo.more = frame.more;
      convo.loaded = true;
      convo.loading = false;
    } else {
      this.error = null;
      const me = this.state?.me.id;
      const fresh = frame.msgs.filter((m) => m.from !== me && !convo.log.lines.some((l) => l.id === m.id));
      if (this.active === frame.with.id) this.readActive(newest?.id);
      else convo.unread += fresh.length;
    }
    convo.log.receive({ t: "chat", msgs: frame.msgs.map(toLine), history: frame.history });
  }

  /** The conversation with someone, started empty if there is none yet. */
  conversation(p: Person): Conversation {
    let convo = this.conversations.get(p.id);
    if (!convo) {
      convo = { ...paged(), with: person(p), last: null, unread: 0 };
      this.conversations.set(p.id, convo);
    }
    return convo;
  }

  /** Conversations with at least one line, the latest first. */
  sortedConversations(): Conversation[] {
    return [...this.conversations.values()]
      .filter((c) => c.last)
      .sort((a, b) => b.last!.id - a.last!.id || a.with.name.localeCompare(b.with.name));
  }

  /** Show a conversation (or none): fetch its first page if needed and mark it read. */
  open(id: number | null): void {
    this.active = id;
    if (id !== null) {
      const convo = this.conversations.get(id);
      if (convo && !convo.loaded && !convo.loading) {
        convo.loading = this.send({ t: "history", with: id });
      }
      this.readActive();
    }
    this.changed();
  }

  /** Ask for the page before the oldest line shown (``null`` = the public room). */
  loadOlder(id: number | null): void {
    const target = id === null ? this.publicRoom : this.conversations.get(id);
    if (!target || !target.more || target.loading) return;
    const before = target.log.lines[0]?.id;
    target.loading = this.send({ t: "history", with: id, ...(before ? { before } : {}) });
    this.changed();
  }

  private readActive(upto?: number): void {
    const convo = this.active === null ? undefined : this.conversations.get(this.active);
    if (!convo) return;
    const last = upto ?? convo.last?.id;
    const hadUnread = convo.unread > 0;
    convo.unread = 0;
    if (last !== undefined && (hadUnread || upto !== undefined)) this.send({ t: "read", with: convo.with.id, upto: last });
  }

  clearError(): void {
    if (!this.error) return;
    this.error = null;
    this.changed();
  }

  /** Unread private messages. */
  unreadMessages(): number {
    let n = 0;
    for (const c of this.conversations.values()) n += c.unread;
    return n;
  }

  /** Unread private messages plus friend requests waiting for an answer: the number on the button. */
  attention(): number {
    return this.unreadMessages() + (this.state?.incoming.length ?? 0);
  }

  isFriend(id: number): boolean {
    return !!this.state?.friends.some((f) => f.id === id);
  }

  /** Whether a friend request to this person (or from them) is already waiting. */
  isPending(id: number): boolean {
    return !!this.state && [...this.state.incoming, ...this.state.outgoing].some((p) => p.id === id);
  }
}
