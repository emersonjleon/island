// The chat on the game page: a round button with an unread badge next to the
// camera buttons, a short preview of new lines, and a panel that stays open
// beside the board (and above the trade dialog, to talk while trading).
import type { TFunction } from "i18next";
import { useEffect, useState } from "preact/hooks";

import "./chat.css";
import { chatErrorKey } from "./i18n";
import type { ChatLine, ChatLog } from "./model";
import { ChatText, ChatView } from "./ChatView";

export interface GameChat {
  log: ChatLog;
  /** Send a line over the game socket; false while it is not connected. */
  send(text: string): boolean;
}

const PEEK_MS = 5000;
const PREVIEWS_KEY = "island.chat.previews";

function readPreviews(): boolean {
  try {
    return localStorage.getItem(PREVIEWS_KEY) !== "off";
  } catch {
    return true;
  }
}

function writePreviews(on: boolean): void {
  try {
    localStorage.setItem(PREVIEWS_KEY, on ? "on" : "off");
  } catch {
    // private window: the choice lasts until the page closes
  }
}

function useLog(log: ChatLog): void {
  const [, setN] = useState(0);
  useEffect(() => log.subscribe(() => setN((n) => n + 1)), [log]);
}

const Bubble = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
    <path d="M4 5.5h16a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5h-9l-4.5 3.5v-3.5H4A1.5 1.5 0 0 1 2.5 16V7A1.5 1.5 0 0 1 4 5.5z"
          fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" />
    <path d="M7 10h10M7 13.5h6" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
  </svg>
);

/** The button (with a preview of the newest line while the panel is closed). */
export function ChatToggle({ chat, t }: { chat: GameChat; t: TFunction }) {
  const { log } = chat;
  useLog(log);
  const [peek, setPeek] = useState<ChatLine | null>(null);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const off = log.subscribe((l, fresh) => {
      if (l.open || !fresh.length || !readPreviews()) return;
      setPeek(fresh[fresh.length - 1]!);
      clearTimeout(timer);
      timer = setTimeout(() => setPeek(null), PEEK_MS);
    });
    return () => { off(); clearTimeout(timer); };
  }, [log]);
  const toggle = () => { setPeek(null); log.setOpen(!log.open); };
  const label = log.unread ? `${t("chat:open")} · ${t("chat:unread", { count: log.unread })}` : t("chat:open");
  return (
    <div class="chat-dock">
      {peek && !log.open && (
        <button type="button" class="chat-peek" onClick={toggle}>
          <strong>{peek.name}:</strong> <ChatText text={peek.text} t={t} />
        </button>
      )}
      <button type="button" class="chat-toggle" onClick={toggle} aria-expanded={log.open} aria-label={label} title={label}>
        <Bubble />
        {log.unread > 0 && <span class="chat-badge">{log.unread > 99 ? "99+" : log.unread}</span>}
      </button>
    </div>
  );
}

/** The panel; it does not block the board, so the game goes on while you talk. */
export function ChatPanel({ chat, t, touch }: { chat: GameChat; t: TFunction; touch: boolean }) {
  const { log } = chat;
  useLog(log);
  const [previews, setPreviews] = useState(readPreviews);
  if (!log.open) return null;
  const close = () => log.setOpen(false);
  const flip = () => { writePreviews(!previews); setPreviews(!previews); };
  return (
    <section class="chat-panel" role="dialog" aria-label={t("chat:title")}
             onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } }}>
      <header>
        <h2>{t("chat:title")}</h2>
        <button type="button" class="chat-previews" aria-pressed={!previews} onClick={flip}
                title={t(previews ? "chat:previews_off" : "chat:previews_on")}
                aria-label={t(previews ? "chat:previews_off" : "chat:previews_on")}>
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" />
            {!previews && <path d="M4 4l16 16" stroke="currentColor" stroke-width="2" stroke-linecap="round" />}
          </svg>
        </button>
        <button type="button" class="chat-close" onClick={close} aria-label={t("chat:close")} title={t("chat:close")}>✕</button>
      </header>
      <ChatView log={log} t={t} send={chat.send} quick autoFocus={!touch}
                error={log.error ? t(chatErrorKey(log.error.code), log.error.params) : null} />
    </section>
  );
}
