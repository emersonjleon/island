// Lobby page entry: live seat updates for /lobby/<code>/.
import { initI18n, pageLanguage } from "../i18n";
import { connectLobby } from "../lobby/live";

void initI18n(pageLanguage());

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
  };
  connectLobby(wsPath, page);
  setInterval(() => {
    if (!leaving && root.querySelector("[data-starting]")) void page.refreshSeats();
  }, STARTING_POLL_MS);
}
