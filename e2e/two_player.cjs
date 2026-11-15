// Two-player smoke test: sign up, create and join a game in the lobby, place the
// setup pieces with the keyboard, see a dice roll, then build until someone wins.
// Run through e2e/run.py, which starts the servers with e2e/settings.py
// (short game, lots of resources). Usage: node e2e/two_player.cjs BASE_URL OUT_DIR
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const STEP_TIMEOUT_MS = 60_000;
const GAME_TIMEOUT_MS = 240_000;

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function signUp(page, name) {
  await page.goto(`${BASE}/accounts/signup/`);
  const names = await page.$$eval("main form input", (is) => is.map((i) => i.name));
  for (const n of names) {
    if (n === "csrfmiddlewaretoken" || n.startsWith("initial-")) continue;
    const value = /pass/.test(n) ? PASSWORD : /mail/.test(n) ? `${name}@example.com` : name;
    await page.fill(`main form input[name="${n}"]`, value);
  }
  await Promise.all([page.waitForNavigation(), page.click("main form button[type=submit]")]);
  if (page.url().includes("/signup/")) throw new Error(`sign-up failed for ${name}: ${await page.textContent("main")}`);
}

/** Facts about this page's player, read from the game client's store. */
function me(page) {
  return page.evaluate(() => {
    const st = window.island?.store;
    const s = st?.state;
    if (!s || st.seat === null) return null;
    const p = s.players.find((x) => x.seat === st.seat);
    return {
      phase: s.phase, clock: s.clock_started, setupDone: p.setup.done, remaining: p.setup.remaining,
      points: p.points ?? 0, buildable: s.buildable ?? { roads: [], settlements: [], cities: [] },
      busy: s.constructions.some((c) => c.seat === st.seat),
      walking: s.settlers.some((x) => x.seat === st.seat && (x.step || x.path.length)), winner: s.winner, lastRoll: s.last_roll,
      mode: window.island.input.mode,
    };
  });
}

async function waitFor(fn, what, timeout = STEP_TIMEOUT_MS) {
  const t0 = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - t0 > timeout) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 250));
  }
}

/** Press a build key, then Enter on the candidate the game picked. */
async function buildWithKeys(page, key) {
  await page.keyboard.press(key);
  await page.waitForTimeout(150);
  const mode = await page.evaluate(() => window.island.input.mode);
  if (!mode || mode.focus === null) {
    await page.keyboard.press("Escape");
    return false;
  }
  await page.keyboard.press("Enter");
  return true;
}

/** Setup: walk and build the setup settlements and roads, all with the keyboard. */
async function playSetup(page, who) {
  await waitFor(async () => (await me(page)) !== null, `${who}'s game state`);
  const t0 = Date.now();
  for (;;) {
    const m = await me(page);
    if (m.setupDone) return;
    if (Date.now() - t0 > STEP_TIMEOUT_MS * 2) throw new Error(`${who} could not finish setup`);
    if (!m.busy) {
      const want = (m.remaining.settlement ?? 0) > 0 && m.buildable.settlements.length ? "KeyE"
        : (m.remaining.road ?? 0) > 0 && m.buildable.roads.length ? "KeyR" : null;
      if (want && (await buildWithKeys(page, want))) {
        // Wait until the order turned into a construction (the settler may walk first).
        await waitFor(async () => {
          const n = await me(page);
          return n.busy || n.walking || n.setupDone || JSON.stringify(n.remaining) !== JSON.stringify(m.remaining);
        }, `${who}'s setup build`, 30_000).catch(async () => log(who, "retrying a setup build", JSON.stringify({ want, ...(await me(page)), buildable: undefined })));
      }
    }
    await page.waitForTimeout(300);
  }
}

/** Development cards through the HUD: buy one, wait for the next roll, play it. */
async function buyAndPlayCard(page) {
  const cards = () => page.evaluate(() => {
    const st = window.island.store;
    return st.state.dev_cards?.players[String(st.seat)]?.cards ?? [];
  });
  await page.click(".hud-hand .actions button.buy-card");
  await waitFor(async () => (await cards()).length > 0, "a bought development card");
  const rolls = await page.evaluate(() => window.island.store.state.dice_history.length);
  await waitFor(() => page.evaluate((n) => window.island.store.state.dice_history.length > n, rolls), "the next dice roll");
  const played = () => page.evaluate(() => window.island.store.lastEvents.some((e) => e.k === "dev_card_played")
    || window.island.store.state.dev_cards.players[String(window.island.store.seat)].last_play != null);
  const [card] = await cards();
  await page.click(".hud-hand .actions button.dev-open");
  const why = await page.textContent(".dev-cards .dev-help");
  if (await page.isDisabled(".dev-cards button.primary")) {
    // e2e/fast_game.json turns the robber off, so a knight can't be played there.
    await page.keyboard.press("Escape");
    return `${card.kind} (not playable here: ${why.trim()})`;
  }
  await page.click(".dev-cards button.primary");
  if (card.kind === "knight") {
    await page.waitForTimeout(150);
    await page.keyboard.press("Enter");                       // the highlighted robber hex
    const who = await page.waitForSelector(".hud-dialog .choices button", { timeout: 1000 }).catch(() => null);
    if (who) await who.click();
  } else if (card.kind === "year_of_plenty" || card.kind === "monopoly") {
    await page.click(".dev-pick button[type=submit]");
  }
  await waitFor(played, `playing the ${card.kind} card`);
  return card.kind;
}

/** Main game: city if possible, else a settlement, else a road; until the game ends. */
async function playToWin(page, who) {
  for (;;) {
    const m = await me(page);
    if (m.phase === "finished") return;
    if (!m.busy) {
      const button = m.buildable.cities.length ? 3 : m.buildable.settlements.length ? 2 : m.buildable.roads.length ? 1 : 0;
      if (button) {
        // Use the HUD build buttons this time, then confirm with Enter.
        // The hand bar goes away when the game ends, so a click may find nothing.
        const clicked = await page.click(`.hud-hand .actions button:nth-child(${button})`, { timeout: 2000 })
          .then(() => true, () => false);
        if (clicked) {
          await page.waitForTimeout(150);
          await page.keyboard.press("Enter");
        }
      }
    }
    await page.waitForTimeout(400);
  }
}

(async () => {
  // E2E_CHROMIUM points at an already-installed Chromium (e.g. in a dev container).
  const browser = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {});
  const ctxA = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const ctxB = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const a = await ctxA.newPage();
  const b = await ctxB.newPage();
  for (const [p, n] of [[a, "ana"], [b, "ben"]]) {
    p.on("pageerror", (e) => { console.error(`${n} page error:`, e.message); process.exitCode = 1; });
    // Server refusals explain most failures; print them.
    p.on("websocket", (ws) => ws.on("framesent", (f) => {
      if (process.env.E2E_TRACE && n === "ana" && !String(f.payload).includes("ping")) log(n, ">>", String(f.payload).slice(0, 200));
    }).on("framereceived", (f) => {
      const text = String(f.payload);
      if (text.includes('"t":"reject"')) log(n, "server refused:", text.slice(0, 200));
      if (process.env.E2E_TRACE && n === "ana" && !text.includes('"pong"')) log(n, "<<", text.slice(0, 400));
    }));
  }
  try {
    log("sign up");
    await signUp(a, "ana");
    await signUp(b, "ben");

    log("ana creates a two-player game");
    await a.goto(`${BASE}/lobby/`);
    await a.selectOption("#id_max_players", "2");
    await Promise.all([a.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), a.click("main form.stacked button[type=submit]")]);
    const code = a.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];
    log("game", code);

    log("ben joins and is ready");
    await b.goto(`${BASE}/lobby/${code}/`);
    await Promise.all([b.waitForNavigation(), b.click(`form[action$="/join/"] button`)]);
    await Promise.all([b.waitForNavigation(), b.click(`form[action$="/ready/"] button`)]);

    log("ana starts; both pages follow to the game");
    await a.reload();
    await Promise.all([
      a.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      b.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      a.click(`form[action$="/start/"] button`),
    ]);

    log("setup with the keyboard");
    await Promise.all([playSetup(a, "ana"), playSetup(b, "ben")]);
    await a.screenshot({ path: `${OUT}/e2e-after-setup.png` });

    log("waiting for a dice roll");
    await waitFor(async () => (await me(a)).lastRoll, "a dice roll");
    await a.waitForSelector(".hud-dice", { timeout: STEP_TIMEOUT_MS });

    log("ana buys a development card and plays it after the next roll");
    log("ana played:", await buyAndPlayCard(a));

    log("building until someone reaches the target");
    const race = Promise.all([playToWin(a, "ana"), playToWin(b, "ben")]);
    let timer;
    const timeout = new Promise((_, rej) => { timer = setTimeout(() => rej(new Error("game did not finish in time")), GAME_TIMEOUT_MS); });
    await Promise.race([race, timeout]).finally(() => clearTimeout(timer));

    for (const [p, n] of [[a, "ana"], [b, "ben"]]) {
      await p.waitForSelector(".hud-overlay .winner", { timeout: STEP_TIMEOUT_MS });
      log(n, "sees:", (await p.textContent(".hud-overlay .winner")).trim());
    }
    const result = await me(a);
    if (result.winner === null || result.winner === undefined) throw new Error("no winner recorded");
    await a.screenshot({ path: `${OUT}/e2e-game-over.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await a.screenshot({ path: `${OUT}/e2e-failure-ana.png` }).catch(() => {});
    await b.screenshot({ path: `${OUT}/e2e-failure-ben.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
