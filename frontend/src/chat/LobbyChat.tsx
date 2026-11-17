// The waiting-room chat on /lobby/<code>/, under the seats. The page's lobby
// socket carries it; the same conversation goes on inside the game.
import type { TFunction } from "i18next";
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";

import "./chat.css";
import { chatErrorKey } from "./i18n";
import type { ChatLog } from "./model";
import { ChatView } from "./ChatView";

function LobbyChat({ log, t, send }: { log: ChatLog; t: TFunction; send(text: string): boolean }) {
  const [, setN] = useState(0);
  useEffect(() => {
    const off = log.subscribe(() => setN((n) => n + 1));
    setN((n) => n + 1);  // lines that arrived between the first render and this subscription
    return off;
  }, [log]);
  return <ChatView log={log} t={t} send={send} error={log.error ? t(chatErrorKey(log.error.code), log.error.params) : null} />;
}

export function mountLobbyChat(el: HTMLElement, log: ChatLog, t: TFunction, send: (text: string) => boolean): void {
  el.innerHTML = "";
  log.setOpen(true);
  render(<LobbyChat log={log} t={t} send={send} />, el);
}
