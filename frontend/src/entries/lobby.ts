// Lobby page entry: live seat updates for /lobby/<code>/.
import { initI18n, pageLanguage } from "../i18n";
import { connectLobby } from "../lobby/live";

void initI18n(pageLanguage());

const root = document.getElementById("lobby-seats");
if (root) {
  const seatsUrl = root.dataset.seatsUrl ?? "";
  const wsPath = root.dataset.wsPath ?? "";
  connectLobby(wsPath, {
    async refreshSeats() {
      const response = await fetch(seatsUrl, { credentials: "same-origin" });
      if (response.ok) root.innerHTML = await response.text();
    },
    navigate(url) {
      window.location.assign(url);
    },
  });
}
