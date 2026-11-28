// The Ages game type: a person picks it in the lobby and plays now against bots.
// The row below the classic hand bar has an "Age II" button with its price; the
// scores show each player's age; the bots play (and may advance) until the end.
// Run through e2e/run.py.
// Usage: node e2e/ages.cjs BASE_URL OUT_DIR
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const GAME_TIMEOUT_MS = 300_000;

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[ages]", ...a);

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
    log("sign up, pick Custom > Ages and play now against bots");
    await signUp(page, "historian");
    await page.goto(`${BASE}/lobby/#create-game`);
    await page.click('.preset-card[data-card="custom"]');                 // ages live inside Custom
    await page.click('[data-base-choice="ages"]');
    if (await page.inputValue('input[name="base"]') !== "ages") throw new Error("Ages was not picked as the base");
    await Promise.all([page.waitForURL(/\/play\/[A-Z0-9]+\/$/, { timeout: 60_000 }), page.click('button[name="play_bots"]')]);
    await page.waitForFunction(() => window.island?.store?.state && window.island?.store?.board);
    const ages = await page.evaluate(() => window.island.store.settings.ages);
    if (!ages?.enabled) throw new Error("ages are not on");
    const button = page.locator(".age-advance");
    await button.waitFor({ timeout: 10_000 });
    const label = ((await button.textContent()) || "").trim();
    log("button:", label);
    if (!/II/.test(label)) throw new Error(`age button does not name age II: ${label}`);
    const rows = await page.evaluate(() => [".build-road", ".age-advance", ".trade-open"]
      .map((sel) => Math.round(document.querySelector(`.hud-hand ${sel}`).getBoundingClientRect().top)));
    if (rows[0] !== rows[2] || rows[1] <= rows[0]) throw new Error(`the classic row changed or the age button is not below it: ${rows}`);
    if (!(await page.locator(".hud-scores .age-tag").count())) throw new Error("scores do not show ages");
    await page.click(".prices-open");
    const priceRows = await page.$$eval(".price-table th", (ths) => ths.map((th) => th.textContent));
    log("prices:", priceRows.join(", "));
    if (!priceRows.some((r) => /II$/.test(r)) || !priceRows.some((r) => /III$/.test(r))) throw new Error("price list misses the ages");
    if (priceRows.filter((r) => /development/i.test(r || "")).length < 3) throw new Error("price list misses the advanced developments");
    await page.keyboard.press("Escape");
    log("the developments menu has a deck per age; the higher ones are locked in age I");
    await page.click(".hud-hand .actions button.dev-open");
    await page.locator(".dev-tier-3").waitFor({ timeout: 5_000 });
    const tiers = await page.$$eval(".dev-buy", (els) => els.map((el) => ({
      cls: el.className, locked: el.querySelector("button.buy-card").disabled, label: el.querySelector("button.buy-card").textContent })));
    log("tiers:", JSON.stringify(tiers));
    if (tiers.length !== 3 || !tiers[1].locked || !tiers[2].locked) throw new Error("tier II and III should be locked in age I");
    await page.screenshot({ path: `${OUT}/e2e-ages-devcards.png` });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/e2e-ages-start.png` });
    await page.setViewportSize({ width: 412, height: 860 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/e2e-ages-phone.png` });
    await page.setViewportSize({ width: 1280, height: 800 });

    log("the bots play until the end");
    const t0 = Date.now();
    let best = 1;
    for (;;) {
      const v = await page.evaluate(() => {
        const { state } = window.island.store;
        const ages = Object.values(state.ages?.players ?? {}).map((p) => p.age);
        return { phase: state.phase, ages, points: state.players.map((p) => p.points) };
      });
      best = Math.max(best, ...v.ages);
      if (v.phase === "finished") { log("finished:", JSON.stringify(v), "highest age:", best); break; }
      if (Date.now() - t0 > GAME_TIMEOUT_MS) throw new Error(`bots did not finish in time: ${JSON.stringify(v)}`);
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: `${OUT}/e2e-ages-end.png` });
    const table = page.locator(".hud-over .stats-ages");
    await table.waitFor({ timeout: 10_000 });
    const cells = await table.locator("tbody td").allTextContents();
    log("ages reached:", cells.join(" | "));
    if (best > 1 && !cells.some((c) => /\d+:\d\d/.test(c))) throw new Error("the results do not say when an age was reached");
    if (best > 1 && !(await page.locator(".hud-over .stats-chart .age-mark").count())) throw new Error("the score chart has no age marks");
    await table.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${OUT}/e2e-ages-results.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await page.screenshot({ path: `${OUT}/e2e-ages-failure.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
