// Resign and statistics on a phone: a desktop player hosts a three-player game, a
// phone player and a second (idle) desktop player join. Once the dice roll, the phone
// opens the statistics (portrait and landscape) and resigns with taps; the game goes
// on. Then the host resigns too, which leaves one player, so the game ends; everyone
// sees the results with the statistics. Run through e2e/run.py.
// Usage: node e2e/resign_stats.cjs BASE_URL OUT_DIR
const { chromium, devices } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const STEP_TIMEOUT_MS = 60_000;
const GAME_TIMEOUT_MS = 240_000;
const PHONE = devices["Pixel 7"];

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[resign]", ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function signUp(page, name) {
  await page.goto(`${BASE}/accounts/signup/`);
  const names = await page.$$eval("main form input", (is) => is.map((i) => i.name));
  for (const n of names) {
    if (n === "csrfmiddlewaretoken" || n.startsWith("initial-")) continue;
    const value = /pass/.test(n) ? PASSWORD : /mail/.test(n) ? `${name}@example.com` : name;
    await page.fill(`main form input[name="${n}"]`, value);
  }
  await Promise.all([page.waitForNavigation(), page.click("main form button[type=submit]")]);
  if (page.url().includes("/signup/")) throw new Error(`sign-up failed for ${name}`);
}

function me(page) {
  return page.evaluate(() => {
    const st = window.island?.store;
    const s = st?.state;
    if (!s || st.seat === null) return null;
    const p = s.players.find((x) => x.seat === st.seat);
    return {
      phase: s.phase, setupDone: p.setup.done, remaining: p.setup.remaining, winner: s.winner, lastRoll: s.last_roll,
      buildable: s.buildable ?? { roads: [], settlements: [], cities: [] },
      busy: s.constructions.some((c) => c.seat === st.seat),
      walking: s.settlers.some((x) => x.seat === st.seat && (x.step || x.path.length)),
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
    await sleep(250);
  }
}

/** Screen point of a build spot; pans the camera to it first if a HUD panel covers it
 * (a person would drag the board). */
async function spotOnScreen(page, kind, id) {
  return page.evaluate(([kind, id]) => {
    const { input, renderer } = window.island;
    const geo = input.geometry();
    const w = kind === "road" ? geo.edgeMid[id] : geo.vertex[id];
    const box = document.querySelector(".game-canvas").getBoundingClientRect();
    const clear = (p) => document.elementFromPoint(box.left + p.x, box.top + p.y)?.tagName === "CANVAS";
    let s = renderer.worldToScreen(w);
    if (!clear(s)) { renderer.centerOn(w); s = renderer.worldToScreen(w); }
    return { x: box.left + s.x, y: box.top + s.y };
  }, [kind, id]);
}

const BUTTON = { road: 1, settlement: 2, city: 3 };

/** Tap a HUD build button, then tap the spot the game highlighted first. */
async function buildByTouch(page, kind) {
  const ok = await page.tap(`.hud-hand .actions button:nth-child(${BUTTON[kind]})`, { timeout: 2000 }).then(() => true, () => false);
  if (!ok) return false;
  await page.waitForTimeout(150);
  const mode = await page.evaluate(() => window.island.input.mode);
  if (!mode || mode.focus === null) {
    // The game can end in between; then the game-over dialog covers the button.
    if (mode) await page.tap(".hud-cancel", { timeout: 2000 }).catch(() => {});
    return false;
  }
  const at = await spotOnScreen(page, kind, mode.focus);
  await page.touchscreen.tap(at.x, at.y);
  return true;
}

async function playSetupByTouch(page) {
  await waitFor(async () => (await me(page)) !== null, "the phone's game state");
  const t0 = Date.now();
  for (;;) {
    const m = await me(page);
    if (m.setupDone) return;
    if (Date.now() - t0 > STEP_TIMEOUT_MS * 2) throw new Error("the phone player could not finish setup");
    if (!m.busy) {
      const want = (m.remaining.settlement ?? 0) > 0 && m.buildable.settlements.length ? "settlement"
        : (m.remaining.road ?? 0) > 0 && m.buildable.roads.length ? "road" : null;
      if (want && (await buildByTouch(page, want))) {
        await waitFor(async () => {
          const n = await me(page);
          return n.busy || n.walking || n.setupDone || JSON.stringify(n.remaining) !== JSON.stringify(m.remaining);
        }, "a setup build from a tap", 30_000).catch(() => log("retrying a setup build"));
      }
    }
    await page.waitForTimeout(300);
  }
}

async function playSetupByKeys(page) {
  await waitFor(async () => (await me(page)) !== null, "the desktop game state");
  for (;;) {
    const m = await me(page);
    if (m.setupDone) return;
    if (!m.busy) {
      const key = (m.remaining.settlement ?? 0) > 0 && m.buildable.settlements.length ? "KeyE"
        : (m.remaining.road ?? 0) > 0 && m.buildable.roads.length ? "KeyR" : null;
      if (key) {
        await page.keyboard.press(key);
        await page.waitForTimeout(150);
        const mode = await page.evaluate(() => window.island.input.mode);
        await page.keyboard.press(mode && mode.focus !== null ? "Enter" : "Escape");
        await page.waitForTimeout(1000);
      }
    }
    await page.waitForTimeout(300);
  }
}

/** Nothing in the page may stick out sideways (that would make the phone page scroll). */
async function checkFits(page, what) {
  const over = await page.evaluate(() => {
    const w = document.documentElement.clientWidth;
    return [...document.querySelectorAll(".game-hud *")]
      .filter((el) => el.getClientRects().length && getComputedStyle(el).visibility !== "hidden")
      .filter((el) => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > w + 1 || r.left < -1); })
      .map((el) => el.className || el.tagName).slice(0, 5);
  });
  if (over.length) throw new Error(`${what}: HUD sticks out of the screen: ${over.join(", ")}`);
}

async function openStats(page, shot) {
  await page.tap(".hud-scores button.stats-open");
  await page.waitForSelector(".hud-dialog .stats .stats-players li");
  await page.waitForTimeout(300);
  await checkFits(page, shot);
  await page.screenshot({ path: `${OUT}/${shot}.png` });
  await page.tap(".hud-dialog header button");
  await page.waitForSelector(".hud-dialog", { state: "detached" });
}

(async () => {
  const browser = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {});
  const desk = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const phone = await (await browser.newContext({ ...PHONE })).newPage();
  const idle = await (await browser.newContext({ viewport: { width: 1024, height: 700 } })).newPage();
  for (const [p, n] of [[desk, "eva"], [phone, "fer"], [idle, "gil"]]) {
    p.on("pageerror", (e) => { console.error(`${n} page error:`, e.message); process.exitCode = 1; });
  }
  try {
    log("sign up; eva hosts three seats, fer joins from the phone, gil from a desktop");
    await signUp(desk, "eva");
    await signUp(phone, "fer");
    await signUp(idle, "gil");
    await desk.goto(`${BASE}/lobby/`);
    await desk.selectOption("#id_max_players", "3");
    await Promise.all([desk.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), desk.click("main form.stacked button[type=submit]")]);
    const code = desk.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];
    await idle.goto(`${BASE}/lobby/${code}/`);
    await Promise.all([idle.waitForNavigation(), idle.click(`form[action$="/join/"] button`)]);
    await Promise.all([idle.waitForNavigation(), idle.click(`form[action$="/ready/"] button`)]);
    await phone.goto(`${BASE}/lobby/${code}/`);
    await Promise.all([phone.waitForNavigation(), phone.tap(`form[action$="/join/"] button`)]);
    await Promise.all([phone.waitForNavigation(), phone.tap(`form[action$="/ready/"] button`)]);
    await desk.reload();
    await Promise.all([
      desk.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      phone.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      idle.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      desk.click(`form[action$="/start/"] button`),
    ]);

    log("setup: the phone builds with taps, the desktop with keys");
    await Promise.all([playSetupByKeys(desk), playSetupByTouch(phone)]);
    await waitFor(async () => (await me(phone)).lastRoll, "a dice roll");

    log("statistics on the phone, portrait and landscape");
    await openStats(phone, "resign-stats-portrait");
    await phone.setViewportSize({ width: PHONE.viewport.height, height: PHONE.viewport.width });
    await phone.waitForTimeout(500);
    await checkFits(phone, "landscape with the new buttons");
    await openStats(phone, "resign-stats-landscape");

    log("the phone player resigns (landscape)");
    await phone.tap(".hud-scores button.resign-open");
    await phone.waitForSelector(".hud-dialog .resign-body");
    await phone.screenshot({ path: `${OUT}/resign-confirm-landscape.png` });
    await phone.tap(".hud-dialog button.danger");
    await phone.waitForSelector(".hud-resigned", { timeout: STEP_TIMEOUT_MS });
    const after = await me(phone);
    if (after.phase !== "running") throw new Error(`the game should go on after one resignation, phase ${after.phase}`);
    if (await phone.locator(".hud-hand").count()) throw new Error("the hand bar is still shown after resigning");
    await phone.setViewportSize(PHONE.viewport);
    await phone.waitForTimeout(500);
    await checkFits(phone, "portrait after resigning");
    await phone.screenshot({ path: `${OUT}/resign-watching-portrait.png` });
    const seen = await desk.evaluate(() => window.island.store.state.players.filter((p) => p.resigned).map((p) => p.name));
    if (!seen.includes("fer")) throw new Error(`the desktop does not show fer as resigned: ${seen}`);

    log("eva resigns too: only gil is left, so the game ends");
    await desk.click(".hud-scores button.resign-open");
    await desk.click(".hud-dialog button.danger");
    for (const [page, name] of [[desk, "desktop"], [phone, "phone"], [idle, "gil"]]) {
      await page.waitForSelector(".hud-over .stats", { timeout: STEP_TIMEOUT_MS });
      const reason = await page.textContent(".hud-over .over-reason");
      if (!reason) throw new Error(`${name}: no resign reason on the results`);
    }
    await desk.screenshot({ path: `${OUT}/resign-game-over-desktop.png` });
    await phone.waitForTimeout(300);
    await checkFits(phone, "results portrait");
    await phone.screenshot({ path: `${OUT}/resign-game-over-portrait.png` });
    await phone.setViewportSize({ width: PHONE.viewport.height, height: PHONE.viewport.width });
    await phone.waitForTimeout(400);
    await checkFits(phone, "results landscape");
    await phone.screenshot({ path: `${OUT}/resign-game-over-landscape.png` });

    log("results can be hidden to see the board, and shown again");
    await phone.tap(".over-buttons button");
    await phone.waitForSelector(".hud-over", { state: "detached" });
    await phone.tap(".hud-clock button.primary");
    await phone.waitForSelector(".hud-over .stats");
    log("PASS");
  } catch (err) {
    console.error("FAIL [resign]:", err.message);
    await phone.screenshot({ path: `${OUT}/resign-failure.png` }).catch(() => {});
    await desk.screenshot({ path: `${OUT}/resign-failure-desktop.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
