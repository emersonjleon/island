// Phone smoke test: one player on a desktop browser, one on an emulated phone with
// a touch screen. The phone player does everything with taps (HUD build buttons,
// then a tap on the highlighted spot), in portrait and then in landscape, and the
// test saves screenshots of both layouts. Run through e2e/run.py.
// Usage: node e2e/phone.cjs BASE_URL OUT_DIR
const { chromium, devices } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const STEP_TIMEOUT_MS = 60_000;
const GAME_TIMEOUT_MS = 240_000;
const PHONE = devices["Pixel 7"];

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[phone]", ...a);
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

async function playToWin(page, touch) {
  for (;;) {
    const m = await me(page);
    if (m.phase === "finished") return;
    if (!m.busy) {
      const kind = m.buildable.cities.length ? "city" : m.buildable.settlements.length ? "settlement" : m.buildable.roads.length ? "road" : null;
      if (kind && touch) await buildByTouch(page, kind);
      else if (kind) {
        const clicked = await page.click(`.hud-hand .actions button:nth-child(${BUTTON[kind]})`, { timeout: 2000 }).then(() => true, () => false);
        if (clicked) { await page.waitForTimeout(150); await page.keyboard.press("Enter"); }
      }
    }
    await page.waitForTimeout(400);
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

(async () => {
  const browser = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {});
  const desk = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const phone = await (await browser.newContext({ ...PHONE })).newPage();
  for (const [p, n] of [[desk, "cam"], [phone, "dia"]]) {
    p.on("pageerror", (e) => { console.error(`${n} page error:`, e.message); process.exitCode = 1; });
    p.on("websocket", (ws) => ws.on("framereceived", (f) => {
      const text = String(f.payload);
      if (text.includes('"t":"reject"')) log(n, "server refused:", text.slice(0, 200));
    }));
  }
  try {
    log("sign up (the phone signs up on its small screen)");
    await signUp(desk, "cam");
    await signUp(phone, "dia");

    log("cam creates a game on the desktop; dia joins from the phone");
    await desk.goto(`${BASE}/lobby/`);
    await desk.selectOption("#id_max_players", "2");
    await Promise.all([desk.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), desk.click("main form.stacked button[type=submit]")]);
    const code = desk.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];
    await phone.goto(`${BASE}/lobby/${code}/`);
    await Promise.all([phone.waitForNavigation(), phone.tap(`form[action$="/join/"] button`)]);
    await Promise.all([phone.waitForNavigation(), phone.tap(`form[action$="/ready/"] button`)]);
    await phone.screenshot({ path: `${OUT}/phone-lobby.png` });
    await desk.reload();
    await Promise.all([
      desk.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      phone.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      desk.click(`form[action$="/start/"] button`),
    ]);

    log("setup: the phone builds with taps");
    await waitFor(async () => (await me(phone)) !== null, "the phone's game state");
    await phone.waitForTimeout(500);
    await phone.screenshot({ path: `${OUT}/phone-portrait-setup.png` });
    await checkFits(phone, "portrait");
    await Promise.all([playSetupByKeys(desk), playSetupByTouch(phone)]);

    log("waiting for a dice roll");
    await waitFor(async () => (await me(phone)).lastRoll, "a dice roll");
    await phone.screenshot({ path: `${OUT}/phone-portrait-running.png` });

    const target = await phone.evaluate(() => {
      const { store, input, renderer } = window.island;
      const mine = store.state.settlers.find((s) => s.seat === store.seat);
      if (!mine) return null;  // this game's settlers retire after setup
      const board = store.board;
      const next = board.vertices[mine.vertex].adj_e.map((e) => board.edges[e].v.find((v) => v !== mine.vertex))
        .find((v) => board.vertices[v].hexes.some((h) => board.hexes[h].land));
      renderer.centerOn(input.geometry().vertex[next]);
      return next;
    });
    if (target !== null) {
      log("a tap on the board walks the settler there");
      const at = await spotOnScreen(phone, "settlement", target);
      await phone.touchscreen.tap(at.x, at.y);
      // A menu appears when something can be built there; choose "walk".
      const menu = await phone.waitForSelector(".game-menu button", { timeout: 1000 }).catch(() => null);
      if (menu) await menu.tap();
      await waitFor(async () => phone.evaluate((v) => {
        const { store } = window.island;
        return store.state.settlers.some((s) => s.seat === store.seat && (s.vertex === v || s.step?.to_v === v || s.path.includes(v)));
      }, target), "the settler to walk where the phone tapped", 10_000);
    }

    log("landscape");
    await phone.setViewportSize({ width: PHONE.viewport.height, height: PHONE.viewport.width });
    await phone.waitForTimeout(600);
    await phone.screenshot({ path: `${OUT}/phone-landscape-running.png` });
    await checkFits(phone, "landscape");

    log("trade dialog on the phone");
    await phone.tap(".hud-hand .actions button:nth-child(4)");
    await phone.waitForSelector(".hud-dialog");
    await phone.screenshot({ path: `${OUT}/phone-landscape-trade.png` });
    await phone.tap(".hud-dialog header button");

    log("back to portrait; building until someone wins");
    await phone.setViewportSize(PHONE.viewport);
    const race = Promise.all([playToWin(desk, false), playToWin(phone, true)]);
    let timer;
    const timeout = new Promise((_, rej) => { timer = setTimeout(() => rej(new Error("game did not finish in time")), GAME_TIMEOUT_MS); });
    await Promise.race([race, timeout]).finally(() => clearTimeout(timer));
    await phone.waitForSelector(".hud-overlay .winner", { timeout: STEP_TIMEOUT_MS });
    log("dia sees:", (await phone.textContent(".hud-overlay .winner")).trim());
    await phone.screenshot({ path: `${OUT}/phone-game-over.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL [phone]:", err.message);
    await phone.screenshot({ path: `${OUT}/phone-failure.png` }).catch(() => {});
    await desk.screenshot({ path: `${OUT}/phone-failure-desktop.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
