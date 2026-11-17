// Reconnection: two players mid-game; ana's browser goes offline for a while and
// comes back. Her page must say it lost the connection (and refuse orders instead
// of losing them), ben must see her as offline, the game must go on without her,
// and once she is back her page must catch up with the game and ben must see her
// online again. Finally ben reloads his page mid-game and gets his seat back.
// Usage: node e2e/reconnect.cjs BASE_URL OUT_DIR (run through e2e/run.py).
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const STEP_TIMEOUT_MS = 60_000;

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[reconnect]", ...a);

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

const rolls = (page) => page.evaluate(() => window.island.store.state.dice_history.length);
const offlineTags = (page) => page.$$eval(".hud-scores .tag.offline", (els) => els.length);

(async () => {
  const browser = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {});
  const ctxA = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const ctxB = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const a = await ctxA.newPage();
  const b = await ctxB.newPage();
  for (const [p, n] of [[a, "rita"], [b, "rob"]]) {
    p.on("pageerror", (e) => { console.error(`${n} page error:`, e.message); process.exitCode = 1; });
  }
  try {
    log("sign up; rita creates a two-player game and rob joins");
    await signUp(a, "rita");
    await signUp(b, "rob");
    await a.goto(`${BASE}/lobby/`);
    await a.selectOption("#id_max_players", "2");
    await Promise.all([a.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), a.click("main form.stacked button[type=submit]")]);
    const code = a.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];
    await b.goto(`${BASE}/lobby/${code}/`);
    await Promise.all([b.waitForNavigation(), b.click(`form[action$="/join/"] button`)]);
    await Promise.all([b.waitForNavigation(), b.click(`form[action$="/ready/"] button`)]);
    await a.reload();
    await Promise.all([
      a.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      b.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      a.click(`form[action$="/start/"] button`),
    ]);

    log("setup, then wait for the dice");
    await Promise.all([playSetup(a, "rita"), playSetup(b, "rob")]);
    await waitFor(async () => (await me(a)).lastRoll, "a dice roll");
    if (await offlineTags(b)) throw new Error("rob sees someone offline before anything happened");

    log("rita's browser goes offline");
    await ctxA.setOffline(true);
    await a.waitForSelector(".hud-offline", { timeout: 10_000 });
    log("rita sees:", (await a.textContent(".hud-offline")).trim());
    const sent = await a.evaluate(() => window.island.connection.send({ a: "buy_dev_card" }));
    if (sent !== null) throw new Error("an order went out while offline");
    await waitFor(async () => (await offlineTags(b)) === 1, "rob to see rita offline", 20_000);
    log("rob sees rita offline:", (await b.textContent(".hud-scores .tag.offline")).trim());
    await a.screenshot({ path: `${OUT}/e2e-reconnect-offline.png` });

    log("the game goes on without her");
    const before = await rolls(b);
    await waitFor(async () => (await rolls(b)) >= before + 2, "two more dice rolls on rob's page", 30_000);

    log("rita comes back");
    await ctxA.setOffline(false);
    await a.waitForSelector(".hud-offline", { state: "detached", timeout: 20_000 });
    await waitFor(async () => (await rolls(a)) >= (await rolls(b)) - 1 && (await rolls(a)) > before + 1,
      "rita's page to catch up with the dice", 20_000);
    await waitFor(async () => (await offlineTags(b)) === 0, "rob to see rita online again", 20_000);
    log("rita caught up:", await rolls(a), "rolls; rob:", await rolls(b));

    log("rob reloads his page mid-game and gets his seat back");
    const seat = await b.evaluate(() => window.island.store.seat);
    const points = (await me(b)).points;
    await b.reload();
    await waitFor(async () => (await me(b)) !== null, "rob's game state after the reload");
    const after = await me(b);
    if (await b.evaluate(() => window.island.store.seat) !== seat || after.points < points) {
      throw new Error("rob lost his seat or his points on reload");
    }
    await waitFor(async () => (await offlineTags(a)) === 0, "rita to see rob online after his reload", 20_000);
    log("PASS");
  } catch (err) {
    console.error("FAIL [reconnect]:", err.message);
    await a.screenshot({ path: `${OUT}/e2e-reconnect-failure-rita.png` }).catch(() => {});
    await b.screenshot({ path: `${OUT}/e2e-reconnect-failure-rob.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
