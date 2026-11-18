// Lobby page entry: live seat updates and the waiting-room chat for /lobby/<code>/.
import type { TFunction } from "i18next";

import { addChatCatalogue } from "../chat/i18n";
import { mountLobbyChat } from "../chat/LobbyChat";
import { ChatLog, type ChatFrame } from "../chat/model";
import { initI18n, pageLanguage } from "../i18n";
import { connectLobby } from "../lobby/live";
import { initCopyButtons } from "../lobby/share";

const ready = initI18n(pageLanguage()).then((i18n) => {
  addChatCatalogue(i18n);
  return i18n.t.bind(i18n) as TFunction;
});
const chatLog = new ChatLog();

/** While the island is being prepared, re-check this often, in case the
 * "started" message arrived before this page's WebSocket was connected. */
const STARTING_POLL_MS = 2000;

/** How long after a seat form is sent its result page still counts as "this page saw the start". */
const SUBMIT_FOLLOW_MS = 30000;
const SUBMIT_KEY = `island.lobby.submitted:${location.pathname}`;

function rememberSubmit(): void {
  try {
    sessionStorage.setItem(SUBMIT_KEY, String(Date.now()));
  } catch {
    // storage blocked: the page falls back to the "Go to the game" button
  }
}

function justSubmitted(): boolean {
  try {
    const at = Number(sessionStorage.getItem(SUBMIT_KEY));
    sessionStorage.removeItem(SUBMIT_KEY);
    return at > 0 && Date.now() - at < SUBMIT_FOLLOW_MS;
  } catch {
    return false;
  }
}

const shareBox = document.querySelector<HTMLElement>("[data-share-code]");
if (shareBox) initCopyButtons(shareBox);

/** The refusal of the last background action, shown above the seats after they refresh. */
let quickError = "";

async function quickPost(form: HTMLFormElement, body: FormData): Promise<void> {
  try {
    const response = await fetch(form.action, {
      method: "POST", body, credentials: "same-origin",
      headers: { "X-Lobby-Quick": "1" },
    });
    if (!response.ok) quickError = await response.text();
  } catch {
    form.submit();
  }
}

const root = document.getElementById("lobby-seats");
if (root) {
  const seatsUrl = root.dataset.seatsUrl ?? "";
  const wsPath = root.dataset.wsPath ?? "";
  // Only a page that saw the game starting follows it on its own; someone who
  // opens the lobby of a running game gets the "Go to the game" button instead.
  let waiting = root.querySelector("[data-starting]") !== null || justSubmitted();
  let leaving = false;
  const go = (url: string) => {
    if (leaving) return;
    leaving = true;
    window.location.assign(url);
  };
  // A seat form (Start, Ready, ...) that is being submitted already navigates; following
  // "started" at the same time would abort that request. The page it lands on follows instead,
  // even when the game is already running by then (it would otherwise only show the button).
  window.addEventListener("submit", (e) => {
    if (e.defaultPrevented) return;
    leaving = true;
    rememberSubmit();
  });
  const page = {
    async refreshSeats() {
      const response = await fetch(seatsUrl, { credentials: "same-origin" });
      if (!response.ok) return;
      root.innerHTML = await response.text();
      if (quickError) {
        const note = document.createElement("p");
        note.className = "error";
        note.textContent = quickError;
        root.prepend(note);
        quickError = "";
      }
      const link = root.querySelector<HTMLAnchorElement>("a[data-game-url]");
      if (waiting && link) go(link.href);
      waiting = waiting || root.querySelector("[data-starting]") !== null;
    },
    navigate: go,
    chat: (frame: ChatFrame) => { chatLog.receive(frame); },
    notice: (code: string, params: Record<string, unknown>) => { if (code.startsWith("chat.")) chatLog.refused(code, params); },
  };
  // Bot buttons (data-quick) post in the background and refresh only the seats, so
  // adding or removing bots does not reload the page.
  root.addEventListener("submit", (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-quick")) return;
    e.preventDefault();
    const submitter = e.submitter instanceof HTMLButtonElement ? e.submitter : null;
    const body = new FormData(form, submitter); // before disabling: a disabled button sends nothing
    for (const b of form.querySelectorAll("button")) b.disabled = true;
    void quickPost(form, body).finally(() => void page.refreshSeats());
  });
  const running = root.querySelector<HTMLAnchorElement>("a[data-game-url]");
  if (waiting && running) go(running.href);
  const socket = connectLobby(wsPath, page);
  const chatRoot = document.getElementById("lobby-chat");
  if (chatRoot) {
    void ready.then((t) => mountLobbyChat(chatRoot, chatLog, t, (text) => socket.send({ t: "chat", text })));
  }
  setInterval(() => {
    if (!leaving && root.querySelector("[data-starting]")) void page.refreshSeats();
  }, STARTING_POLL_MS);
}
