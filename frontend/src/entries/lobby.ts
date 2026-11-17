// Lobby page entry: live seat updates and the waiting-room chat for /lobby/<code>/.
import type { TFunction } from "i18next";

import { addChatCatalogue } from "../chat/i18n";
import { mountLobbyChat } from "../chat/LobbyChat";
import { ChatLog, type ChatFrame } from "../chat/model";
import { initI18n, pageLanguage } from "../i18n";
import { connectLobby } from "../lobby/live";

const ready = initI18n(pageLanguage()).then((i18n) => {
  addChatCatalogue(i18n);
  return i18n.t.bind(i18n) as TFunction;
});
const chatLog = new ChatLog();

/** While the island is being prepared, re-check this often, in case the
 * "started" message arrived before this page's WebSocket was connected. */
const STARTING_POLL_MS = 2000;

const root = document.getElementById("lobby-seats");
if (root) {
  const seatsUrl = root.dataset.seatsUrl ?? "";
  const wsPath = root.dataset.wsPath ?? "";
  // Only a page that saw the game starting follows it on its own; someone who
  // opens the lobby of a running game gets the "Go to the game" button instead.
  let waiting = root.querySelector("[data-starting]") !== null;
  let leaving = false;
  const go = (url: string) => {
    if (leaving) return;
    leaving = true;
    window.location.assign(url);
  };
  const page = {
    async refreshSeats() {
      const response = await fetch(seatsUrl, { credentials: "same-origin" });
      if (!response.ok) return;
      root.innerHTML = await response.text();
      const link = root.querySelector<HTMLAnchorElement>("a[data-game-url]");
      if (waiting && link) go(link.href);
      waiting = waiting || root.querySelector("[data-starting]") !== null;
    },
    navigate: go,
    chat: (frame: ChatFrame) => { chatLog.receive(frame); },
    notice: (code: string, params: Record<string, unknown>) => { if (code.startsWith("chat.")) chatLog.refused(code, params); },
  };
  const socket = connectLobby(wsPath, page);
  const chatRoot = document.getElementById("lobby-chat");
  if (chatRoot) {
    void ready.then((t) => mountLobbyChat(chatRoot, chatLog, t, (text) => socket.send({ t: "chat", text })));
  }
  setInterval(() => {
    if (!leaving && root.querySelector("[data-starting]")) void page.refreshSeats();
  }, STARTING_POLL_MS);
}
