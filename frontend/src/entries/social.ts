// Site-wide chat entry: the public room, friends and private messages panel.
// Any page can load it with {% include "chat/_social_chat.html" %} and {% vite_entry "social" %}.
import type { TFunction } from "i18next";

import { addChatCatalogue } from "../chat/i18n";
import { mountSocialPanel } from "../chat/SocialPanel";
import { parseSocialFrame, SocialStore, type SocialFrame, type SocialSend } from "../chat/social";
import { initI18n, pageLanguage } from "../i18n";
import { wsUrl } from "../lobby/live";

const MAX_BACKOFF_MS = 15000;
const PING_MS = 25000;

function connect(path: string, receive: (frame: SocialFrame) => void): SocialSend {
  let socket: WebSocket | null = null;
  let backoff = 500;
  const open = () => {
    socket = new WebSocket(wsUrl(path));
    socket.onopen = () => { backoff = 500; };
    socket.onmessage = (ev: MessageEvent<string>) => {
      try {
        const frame = parseSocialFrame(JSON.parse(ev.data));
        if (frame) receive(frame);
      } catch {
        // ignore malformed frames
      }
    };
    socket.onclose = (ev) => {
      if (ev.code === 4403) return;  // not logged in: nothing to retry
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    };
  };
  open();
  setInterval(() => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ t: "ping" })); }, PING_MS);
  return (frame) => {
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(frame));
    return true;
  };
}

const root = document.getElementById("social-chat");
if (root) {
  let store: SocialStore | null = null;
  const early: SocialFrame[] = [];
  const send = connect(root.dataset.wsPath ?? "/ws/social/", (frame) => (store ? store.receive(frame) : early.push(frame)));
  store = new SocialStore(send);
  for (const frame of early.splice(0)) store.receive(frame);
  void initI18n(pageLanguage()).then((i18n) => {
    addChatCatalogue(i18n);
    mountSocialPanel(root, store!, i18n.t.bind(i18n) as TFunction, send);
  });
}
