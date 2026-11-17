// Phones: go full screen on the first tap of the game page.
//
// Browsers only allow full screen in answer to a tap or a key, never on page load, so
// the closest thing to "open in full screen" is to ask on the very first touch. If the
// player leaves full screen themselves (the button, or the phone's back gesture) the
// choice is remembered and the game stops asking until they go full screen again.
// The installed app (home-screen icon, see static/manifest.webmanifest) always opens in
// full screen and skips all of this.

type FsDoc = Document & { webkitFullscreenEnabled?: boolean; webkitFullscreenElement?: Element | null };
type FsEl = HTMLElement & { webkitRequestFullscreen?: () => void };

const PREF_KEY = "island.autoFullscreen";

function readPref(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) !== "off";
  } catch {
    return true;
  }
}

function writePref(on: boolean): void {
  try {
    localStorage.setItem(PREF_KEY, on ? "on" : "off");
  } catch {
    // Private mode or blocked storage: the choice lasts for this page only.
  }
}

export function isFullscreen(doc: FsDoc = document): boolean {
  return !!(doc.fullscreenElement || doc.webkitFullscreenElement);
}

export function isStandalone(): boolean {
  return matchMedia("(display-mode: standalone), (display-mode: fullscreen)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

/** Calls `onChange` after every switch into or out of full screen, once the page has its new size. */
export function onFullscreenChange(onChange: () => void, settleMs = 350): void {
  const later = () => setTimeout(onChange, settleMs);
  document.addEventListener("fullscreenchange", later);
  document.addEventListener("webkitfullscreenchange", later);
}

/** Asks for full screen on the next tap anywhere on the page (phones only). */
export function enterFullscreenOnFirstTap(): void {
  const doc = document as FsDoc;
  if (!(doc.fullscreenEnabled || doc.webkitFullscreenEnabled) || isStandalone()) return;
  let wanted = readPref();
  const track = () => {
    if (isFullscreen()) {
      wanted = true;
      writePref(true);
    } else if (document.visibilityState === "visible") {
      // Left while the game was on screen: the player's own choice.
      wanted = false;
      writePref(false);
    }
  };
  document.addEventListener("fullscreenchange", track);
  document.addEventListener("webkitfullscreenchange", track);
  // pointerup (not pointerdown) is what counts as a tap for the full-screen permission.
  const tap = (e: PointerEvent) => {
    if (!wanted || isFullscreen() || e.pointerType === "mouse") return;
    const el = document.documentElement as FsEl;
    if (el.requestFullscreen) void el.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
    else el.webkitRequestFullscreen?.();
  };
  document.addEventListener("pointerup", tap, { capture: true, passive: true });
}
