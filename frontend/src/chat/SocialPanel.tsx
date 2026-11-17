// The site-wide chat on the lobby page: a round button with a badge that opens a
// panel with four tabs: the public room, friends (requests, add by name), private
// conversations and the privacy setting. The /ws/social/ socket carries it all.
import type { TFunction } from "i18next";
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

import "./chat.css";
import "./social.css";
import { chatErrorKey } from "./i18n";
import type { ChatLine } from "./model";
import { ChatView } from "./ChatView";
import { PRIVACY, type Person, type Privacy, type SocialStore } from "./social";

export type SocialSend = (frame: object) => boolean;
type Tab = "public" | "friends" | "messages" | "settings";
const TABS: Tab[] = ["public", "friends", "messages", "settings"];
const OPEN_KEY = "island.social.open";
/** Screens at least this wide have room for the panel beside the page, so it starts open there. */
const WIDE_PX = 1280;

function readOpen(): boolean {
  try {
    const saved = localStorage.getItem(OPEN_KEY);
    if (saved) return saved === "1";
  } catch {
    // storage blocked: fall back to the screen width
  }
  return window.matchMedia?.(`(min-width: ${WIDE_PX}px)`).matches ?? false;
}

function writeOpen(open: boolean): void {
  try {
    localStorage.setItem(OPEN_KEY, open ? "1" : "0");
  } catch {
    // private window: the choice lasts until the page closes
  }
}

function useStore(store: SocialStore): void {
  const [, setN] = useState(0);
  useEffect(() => {
    const bump = () => setN((n) => n + 1);
    const offs = [store.subscribe(bump), store.publicLog.subscribe(bump)];
    const watched = new Set<number>();
    const watchConversations = () => {
      for (const [id, c] of store.conversations) {
        if (watched.has(id)) continue;
        watched.add(id);
        offs.push(c.log.subscribe(bump));
      }
    };
    watchConversations();
    offs.push(store.subscribe(watchConversations));
    bump();
    return () => offs.forEach((off) => off());
  }, [store]);
}

function Badge({ n, label }: { n: number; label?: string }) {
  if (n <= 0) return null;
  return <span class="social-badge" aria-label={label}>{n > 99 ? "99+" : n}</span>;
}

interface Props { store: SocialStore; t: TFunction; send: SocialSend }

export function SocialPanel({ store, t, send }: Props) {
  useStore(store);
  const [open, setOpenState] = useState(readOpen);
  const [tab, setTab] = useState<Tab>("public");
  const [talkTo, setTalkTo] = useState<number | null>(null);
  const [picked, setPicked] = useState<Person | null>(null);
  const state = store.state;

  const setOpen = (v: boolean) => {
    setOpenState(v);
    writeOpen(v);
  };
  const go = (next: Tab) => {
    setTab(next);
    store.clearError();
    if (next !== "messages") setTalkTo(null);
  };
  const talk = (p: Person) => {
    store.conversation(p);
    setTalkTo(p.id);
    setTab("messages");
    setPicked(null);
    store.clearError();
  };

  // Lines count as read only in the view that shows them.
  useEffect(() => {
    store.publicLog.setOpen(open && tab === "public");
    for (const [id, c] of store.conversations) c.log.setOpen(open && tab === "messages" && talkTo === id);
  }, [open, tab, talkTo, store.conversations.size]);

  const attention = store.attention();
  const dmUnread = attention - (state?.incoming.length ?? 0);
  const error = store.error ? t(chatErrorKey(store.error.code), store.error.params) : null;

  if (!open) {
    return (
      <button type="button" class="social-fab" onClick={() => setOpen(true)} aria-label={t("chat:social.open")}>
        <span aria-hidden="true">💬</span> {t("chat:social.title")}
        <Badge n={attention} label={t("chat:social.attention", { count: attention })} />
      </button>
    );
  }

  return (
    <section class="social-panel" aria-label={t("chat:social.title")}>
      <header class="social-head">
        <h2>{t("chat:social.title")}</h2>
        {state && <span class="social-me">{state.me.name}</span>}
        <button type="button" class="social-close" onClick={() => setOpen(false)} aria-label={t("chat:close")}>×</button>
      </header>
      <nav class="social-tabs" role="tablist">
        {TABS.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} class={tab === k ? "on" : ""} onClick={() => go(k)}>
            {t(`chat:social.tabs.${k}`)}
            {k === "friends" && <Badge n={state?.incoming.length ?? 0} />}
            {k === "messages" && <Badge n={dmUnread} />}
          </button>
        ))}
      </nav>
      <div class="social-body">
        {!state ? <p class="muted">{t("chat:social.connecting")}</p> : (
          <>
            {tab === "public" && (
              <PublicTab store={store} t={t} send={send} error={error} picked={picked} setPicked={setPicked}
                         talk={talk} toSettings={() => go("settings")} />
            )}
            {tab === "friends" && <FriendsTab store={store} t={t} send={send} error={error} talk={talk} />}
            {tab === "messages" && (
              <MessagesTab store={store} t={t} send={send} error={error} talkTo={talkTo} setTalkTo={setTalkTo}
                           toSettings={() => go("settings")} />
            )}
            {tab === "settings" && <SettingsTab privacy={state.privacy} t={t} send={send} error={error} />}
          </>
        )}
      </div>
    </section>
  );
}

function PublicTab({ store, t, send, error, picked, setPicked, talk, toSettings }: Props & {
  error: string | null; picked: Person | null; setPicked(p: Person | null): void; talk(p: Person): void; toSettings(): void;
}) {
  const state = store.state!;
  if (state.privacy !== "everyone") {
    return (
      <div class="social-note">
        <p>{t("chat:social.public_off")}</p>
        <button type="button" onClick={toSettings}>{t("chat:social.change_setting")}</button>
      </div>
    );
  }
  const onName = (line: ChatLine) => {
    if (line.uid === undefined || line.uid === state.me.id) return;
    setPicked(picked?.id === line.uid ? null : { id: line.uid, name: line.name });
  };
  return (
    <>
      {picked && (
        <div class="social-picked">
          <strong>{picked.name}</strong>
          <button type="button" onClick={() => talk(picked)}>{t("chat:social.message")}</button>
          {store.isFriend(picked.id) ? <span class="muted">{t("chat:social.is_friend")}</span>
            : store.isPending(picked.id) ? <span class="muted">{t("chat:social.pending")}</span>
            : <button type="button" onClick={() => send({ t: "friend", op: "add", id: picked.id })}>{t("chat:social.add_friend")}</button>}
          <button type="button" class="social-x" onClick={() => setPicked(null)} aria-label={t("chat:close")}>×</button>
        </div>
      )}
      <ChatView log={store.publicLog} t={t} plain onName={onName} error={error}
                placeholder={t("chat:social.public_placeholder")}
                send={(text) => send({ t: "say", to: null, text })} />
      <p class="social-hint">{t("chat:social.public_hint")}</p>
    </>
  );
}

function PersonRow({ p, children }: { p: Person; children: preact.ComponentChildren }) {
  return <li class="social-person"><span class="social-name">{p.name}</span><span class="social-actions">{children}</span></li>;
}

function FriendsTab({ store, t, send, error, talk }: Props & { error: string | null; talk(p: Person): void }) {
  const state = store.state!;
  const [name, setName] = useState("");
  const op = (o: "accept" | "remove", p: Person) => send({ t: "friend", op: o, id: p.id });
  const submit = (e: Event) => {
    e.preventDefault();
    const clean = name.trim();
    if (clean && send({ t: "friend", op: "add", name: clean })) setName("");
  };
  return (
    <div class="social-scroll">
      <form class="social-add" onSubmit={submit}>
        <label for="social-add-name">{t("chat:social.add_label")}</label>
        <div>
          <input id="social-add-name" type="text" value={name} maxLength={150} autoComplete="off"
                 placeholder={t("chat:social.add_placeholder")} onInput={(e) => setName(e.currentTarget.value)} />
          <button type="submit" disabled={!name.trim()}>{t("chat:social.send_request")}</button>
        </div>
      </form>
      {error && <p class="chat-error" role="alert">{error}</p>}
      {state.incoming.length > 0 && (
        <>
          <h3>{t("chat:social.incoming")}</h3>
          <ul class="social-people">
            {state.incoming.map((p) => (
              <PersonRow key={p.id} p={p}>
                <button type="button" class="primary" onClick={() => op("accept", p)}>{t("chat:social.accept")}</button>
                <button type="button" onClick={() => op("remove", p)}>{t("chat:social.decline")}</button>
              </PersonRow>
            ))}
          </ul>
        </>
      )}
      <h3>{t("chat:social.friends")}</h3>
      {state.friends.length ? (
        <ul class="social-people">
          {state.friends.map((p) => (
            <PersonRow key={p.id} p={p}>
              <button type="button" onClick={() => talk(p)}>{t("chat:social.message")}</button>
              <button type="button" class="quiet" onClick={() => op("remove", p)}>{t("chat:social.remove")}</button>
            </PersonRow>
          ))}
        </ul>
      ) : <p class="muted">{t("chat:social.no_friends")}</p>}
      {state.outgoing.length > 0 && (
        <>
          <h3>{t("chat:social.outgoing")}</h3>
          <ul class="social-people">
            {state.outgoing.map((p) => (
              <PersonRow key={p.id} p={p}>
                <button type="button" class="quiet" onClick={() => op("remove", p)}>{t("chat:social.cancel")}</button>
              </PersonRow>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function MessagesTab({ store, t, send, error, talkTo, setTalkTo, toSettings }: Props & {
  error: string | null; talkTo: number | null; setTalkTo(id: number | null): void; toSettings(): void;
}) {
  const state = store.state!;
  const convo = talkTo !== null ? store.conversations.get(talkTo) : undefined;
  if (convo) {
    const blocked = state.privacy === "games";
    return (
      <>
        <div class="social-convo-head">
          <button type="button" onClick={() => { setTalkTo(null); store.clearError(); }}>← {t("chat:social.back")}</button>
          <strong>{convo.with.name}</strong>
          {store.isFriend(convo.with.id) && <span class="muted">· {t("chat:social.is_friend")}</span>}
        </div>
        {blocked && (
          <div class="social-note">
            <p>{t("chat:social.dm_off")}</p>
            <button type="button" onClick={toSettings}>{t("chat:social.change_setting")}</button>
          </div>
        )}
        <ChatView log={convo.log} t={t} plain error={error} disabled={blocked} autoFocus={!blocked}
                  placeholder={t("chat:social.dm_placeholder", { name: convo.with.name })}
                  send={(text) => send({ t: "say", to: convo.with.id, text })} />
      </>
    );
  }
  const list = store.sortedConversations().filter((c) => c.log.lines.length > 0);
  return (
    <div class="social-scroll">
      {list.length ? (
        <ul class="social-convos">
          {list.map((c) => {
            const last = c.log.lines[c.log.lines.length - 1];
            return (
              <li key={c.with.id}>
                <button type="button" onClick={() => setTalkTo(c.with.id)}>
                  <span class="social-name">{c.with.name}<Badge n={c.log.unread} /></span>
                  {last && <span class="social-preview">{last.uid === state.me.id ? `${t("chat:you")}: ` : ""}{last.text}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      ) : <p class="muted">{t("chat:social.no_conversations")}</p>}
    </div>
  );
}

function SettingsTab({ privacy, t, send, error }: { privacy: Privacy; t: TFunction; send: SocialSend; error: string | null }) {
  return (
    <div class="social-scroll">
      <fieldset class="social-privacy">
        <legend>{t("chat:social.privacy_title")}</legend>
        {PRIVACY.map((p) => (
          <label key={p} class={privacy === p ? "on" : ""}>
            <input type="radio" name="social-privacy" value={p} checked={privacy === p}
                   onChange={() => send({ t: "privacy", value: p })} />
            <span>
              <strong>{t(`chat:social.privacy.${p}`)}</strong>
              <small>{t(`chat:social.privacy.${p}_help`)}</small>
            </span>
          </label>
        ))}
      </fieldset>
      {error && <p class="chat-error" role="alert">{error}</p>}
      <p class="social-hint">{t("chat:social.privacy_note")}</p>
    </div>
  );
}

export function mountSocialPanel(el: HTMLElement, store: SocialStore, t: TFunction, send: SocialSend): void {
  el.innerHTML = "";
  render(<SocialPanel store={store} t={t} send={send} />, el);
}
