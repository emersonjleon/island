// The conversation itself: lines, a box to write in, resource buttons and quick
// phrases. Used inline on the waiting-room page and inside the game's chat panel.
import type { TFunction } from "i18next";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";

import { RESOURCES } from "../ui/model";
import { ResIcon } from "../ui/icons";
import { playerColour } from "../render2d/palette";
import { clock, dayKey, dayName, fullWhen } from "./dates";
import { RES_EMOJI, splitResources, type ChatLine, type ChatLog } from "./model";

/** Same limit as the server's default (chat.conf MAX_LENGTH); the server has the last word. */
export const MAX_LENGTH = 200;
const QUICK = ["anyone", "deal", "no", "gg"] as const;
/** Pixels from the bottom that still count as "reading the latest lines". */
const STICKY_PX = 40;

export interface ChatViewProps {
  log: ChatLog;
  t: TFunction;
  /** Send a line; false when there is no connection right now. */
  send(text: string): boolean;
  /** The last refusal from the server, already translated. */
  error?: string | null;
  /** Focus the text box when shown (not on touch screens, where it opens the keyboard). */
  autoFocus?: boolean;
  /** Show the quick phrases and resource buttons (trading talk, in the game). */
  quick?: boolean;
  /** Site-wide chat: no player colours, no "watching" tag. */
  plain?: boolean;
  /** Names become buttons that call this (e.g. to write privately or add a friend). */
  onName?(line: ChatLine): void;
  /** Placeholder for the text box instead of the default one. */
  placeholder?: string;
  /** The text box is off (e.g. the privacy setting does not allow writing here). */
  disabled?: boolean;
  /** Older lines exist: show a button at the top that asks for them. */
  onMore?(): void;
  /** Older lines were asked for and have not arrived yet. */
  loadingMore?: boolean;
  /** Lines can be days old (site-wide chat): a heading for each day, the date on hover. */
  dated?: boolean;
  /** Your user id: your own lines are marked so they stand out. */
  me?: number;
}

export function useChatLines(log: ChatLog): ChatLine[] {
  const [, setN] = useState(0);
  useEffect(() => {
    const off = log.subscribe(() => setN((n) => n + 1));
    setN((n) => n + 1);  // lines that arrived between the first render and this subscription
    return off;
  }, [log]);
  return log.lines;
}

function hex(colour: string): string {
  return `#${playerColour(colour).toString(16).padStart(6, "0")}`;
}

export function ChatText({ text, t }: { text: string; t: TFunction }) {
  return (
    <>
      {splitResources(text).map((p, i) => (typeof p === "string" ? p : (
        <span key={i} class={`chat-res res-${p.res}`} role="img" aria-label={t(`chat:res.${p.res}`)} title={t(`chat:res.${p.res}`)}>
          <ResIcon res={p.res} size={16} />
        </span>
      )))}
    </>
  );
}

function pageLocale(): string | undefined {
  return (typeof document !== "undefined" && document.documentElement.lang) || undefined;
}

function DayHeading({ at, t }: { at: number; t: TFunction }) {
  const day = dayName(at, Date.now(), pageLocale());
  const text = day.kind === "date" ? day.text : t(`chat:${day.kind}`);
  return <li class="chat-day" role="separator"><span>{text}</span></li>;
}

export function ChatView({ log, t, send, error, autoFocus, quick, plain, onName, placeholder, disabled, onMore, loadingMore, dated, me }: ChatViewProps) {
  const lines = useChatLines(log);
  const [draft, setDraft] = useState("");
  const [offline, setOffline] = useState(false);
  const list = useRef<HTMLOListElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const sticky = useRef(true);

  // Older lines added on top keep the lines being read where they were.
  const seen = useRef({ first: 0, height: 0 });
  useLayoutEffect(() => {
    const el = list.current;
    if (!el) return;
    const first = lines[0]?.id ?? 0;
    if (sticky.current) el.scrollTop = el.scrollHeight;
    else if (seen.current.first && first < seen.current.first) el.scrollTop += el.scrollHeight - seen.current.height;
    seen.current = { first, height: el.scrollHeight };
  }, [lines.length]);
  useEffect(() => { if (autoFocus) input.current?.focus({ preventScroll: true }); }, [autoFocus]);

  const say = (text: string): boolean => {
    const clean = text.trim();
    if (!clean) return false;
    const ok = send(clean);
    setOffline(!ok);
    if (ok) {
      log.markSent(clean);
      sticky.current = true;
    }
    return ok;
  };
  const submit = (e: Event) => {
    e.preventDefault();
    if (say(draft)) setDraft("");
  };
  const insert = (emoji: string) => {
    const el = input.current;
    const start = el?.selectionStart ?? draft.length;
    const end = el?.selectionEnd ?? draft.length;
    const next = (draft.slice(0, start) + emoji + draft.slice(end)).slice(0, MAX_LENGTH);
    setDraft(next);
    // Keep writing where the icon went (the button took the focus away).
    requestAnimationFrame(() => {
      if (!el) return;
      const at = Math.min(next.length, start + emoji.length);
      el.focus({ preventScroll: true });
      el.setSelectionRange(at, at);
    });
  };

  return (
    <div class={dated ? "chat-view dated" : "chat-view"}>
      <ol class="chat-lines" ref={list} aria-live="polite"
          onScroll={(e) => {
            const el = e.currentTarget;
            sticky.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICKY_PX;
          }}>
        {onMore && (
          <li class="chat-more">
            <button type="button" onClick={onMore} disabled={loadingMore}>{t(loadingMore ? "chat:loading" : "chat:older")}</button>
          </li>
        )}
        {!lines.length && <li class="chat-empty">{t("chat:empty")}</li>}
        {lines.map((m, i) => [
          dated && m.at > 0 && (i === 0 || dayKey(lines[i - 1]!.at) !== dayKey(m.at))
            ? <DayHeading key={`d${m.id}`} at={m.at} t={t} /> : null,
          <li key={m.id} class={[m.player || plain ? "" : "watcher", me !== undefined && m.uid === me ? "mine" : ""].join(" ").trim()}>
            {m.player && !plain && <span class="chat-dot" style={{ background: hex(m.colour) }} aria-hidden="true" />}
            {onName
              ? <button type="button" class="chat-who chat-who-btn" onClick={() => onName(m)}>{m.name}</button>
              : <strong class="chat-who">{m.name}</strong>}
            {!m.player && !plain && <small class="chat-tag"> ({t("chat:watching")})</small>}
            <time class="chat-time" dateTime={m.at ? new Date(m.at).toISOString() : undefined}
                  title={dated ? fullWhen(m.at, pageLocale()) : undefined}>{clock(m.at)}</time>
            <span class="chat-text"><ChatText text={m.text} t={t} /></span>
          </li>,
        ])}
      </ol>
      {(offline || error) && <p class="chat-error" role="alert">{offline ? t("chat:errors.offline") : error}</p>}
      {quick && (
        <div class="chat-quick">
          {QUICK.map((q) => (
            <button key={q} type="button" onClick={() => say(t(`chat:quick.${q}`))}>{t(`chat:quick.${q}`)}</button>
          ))}
        </div>
      )}
      {quick && (
        <div class="chat-res-row">
          {RESOURCES.map((r) => (
            <button key={r} type="button" class={`chat-res-btn res-${r}`} onClick={() => insert(RES_EMOJI[r])}
                    aria-label={t("chat:insert", { res: t(`chat:res.${r}`) })} title={t("chat:insert", { res: t(`chat:res.${r}`) })}>
              <ResIcon res={r} size={16} />
            </button>
          ))}
        </div>
      )}
      <form class="chat-form" onSubmit={submit}>
        <input ref={input} type="text" value={draft} maxLength={MAX_LENGTH} enterKeyHint="send" autoComplete="off"
               placeholder={placeholder ?? t("chat:placeholder")} aria-label={placeholder ?? t("chat:placeholder")}
               disabled={disabled}
               onInput={(e) => setDraft(e.currentTarget.value)}
               onKeyDown={(e) => { if (e.key === "Escape") e.currentTarget.blur(); }} />
        <button type="submit" class="chat-send" disabled={disabled || !draft.trim()}>{t("chat:send")}</button>
      </form>
    </div>
  );
}
