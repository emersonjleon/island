// The Settlers game type: a person picks it in the lobby and plays now against two
// bots. The hand bar has a settler button with its price and "1/N" (N grows with your buildings); the person's
// settler shows its gathering number; the bots buy settlers, gather and finish the
// game. Run through e2e/run.py.
// Usage: node e2e/settlers.cjs BASE_URL OUT_DIR
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const GAME_TIMEOUT_MS = 300_000;

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[settlers]", ...a);

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

(async () => {
  const browser = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {});
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  page.on("pageerror", (e) => { console.error("page error:", e.message); process.exitCode = 1; });
  try {
    log("sign up, pick Custom > Settlers (experimental) and play now against bots");
    await signUp(page, "pioneer");
    await page.goto(`${BASE}/lobby/#create-game`);
    await page.click('.preset-card[data-card="custom"]');
    await page.click('[data-base-choice="settlers"]');
    if (await page.inputValue('input[name="base"]') !== "settlers") throw new Error("Settlers was not picked as the base");
    await Promise.all([page.waitForURL(/\/play\/[A-Z0-9]+\/$/, { timeout: 60_000 }), page.click('button[name="play_bots"]')]);
    await page.waitForFunction(() => window.island?.store?.state && window.island?.store?.board);

    const settings = await page.evaluate(() => window.island.store.settings.settlers);
    log("settings:", JSON.stringify(settings));
    if (settings.leave_after_setup !== false || !settings.gather || !settings.block_robber) throw new Error("not the Settlers rules");
    const button = page.locator(".buy-settler");
    await button.waitFor({ timeout: 10_000 });
    const label = (await button.textContent()) || "";
    log("button:", label.trim());
    if (!/1\/\d+/.test(label)) throw new Error(`settler button does not show 1/N: ${label}`);
    const title = (await button.getAttribute("title")) || "";
    if (!title.includes("11")) throw new Error(`the button does not say the next settler gathers on 11: ${title}`);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/e2e-settlers-start.png` });
    log("on a phone-sized screen the classic row stays, the settler goes in a row below");
    await page.setViewportSize({ width: 412, height: 860 });
    await page.waitForTimeout(400);
    const rows = await page.evaluate(() => [".build-road", ".buy-settler", ".trade-open"]
      .map((sel) => Math.round(document.querySelector(`.hud-hand ${sel}`).getBoundingClientRect().top)));
    await page.screenshot({ path: `${OUT}/e2e-settlers-phone.png` });
    if (rows[0] !== rows[2] || rows[1] <= rows[0]) throw new Error(`the classic row changed or the settler is not below it: ${rows}`);
    log("the price list shows the settler too");
    await page.click(".prices-open");
    const prices = await page.$$eval(".price-table th", (ths) => ths.length);
    await page.screenshot({ path: `${OUT}/e2e-settlers-prices.png` });
    if (prices !== 6) throw new Error(`price list has ${prices} rows, expected 6 (with the megacity and the settler)`);
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.click("canvas", { position: { x: 1200, y: 600 } }).catch(() => {});
    for (const key of ["Space", "Equal", "Equal", "Equal"]) { await page.keyboard.press(key); await page.waitForTimeout(250); }
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/e2e-settlers-zoom.png` });

    log("the bots play until the end; their settlers stay");
    const t0 = Date.now();
    let most = 0;
    for (;;) {
      const v = await page.evaluate(() => {
        const { state } = window.island.store;
        const counts = state.players.map((p) => p.settlers.length);
        return { phase: state.phase, counts, settlers: state.settlers.length };
      });
      most = Math.max(most, ...v.counts);
      if (v.phase === "finished") { log("finished:", JSON.stringify(v), "most settlers:", most); break; }
      if (Date.now() - t0 > GAME_TIMEOUT_MS) throw new Error(`bots did not finish in time: ${JSON.stringify(v)}`);
      await page.waitForTimeout(500);
    }
    if (most < 1) throw new Error("settlers left the game");
    await page.screenshot({ path: `${OUT}/e2e-settlers-end.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await page.screenshot({ path: `${OUT}/e2e-settlers-failure.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
