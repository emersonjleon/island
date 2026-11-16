// A big table: one person and seven computer players (8 seats). Checks the
// lobby's extra colours, the bigger island, the guide for new players, the
// "How to play" dialog and the folded score list on a phone, then waits for a
// bot to win. Run through e2e/run.py. Usage: node e2e/big_table.cjs BASE_URL OUT_DIR
const { chromium, devices } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const PLAYERS = 8;
const STEP_TIMEOUT_MS = 60_000;
const GAME_TIMEOUT_MS = 300_000;

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[big]", ...a);

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
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await desktop.newPage();
  page.on("pageerror", (e) => { console.error("page error:", e.message); process.exitCode = 1; });
  try {
    log("the rules page");
    await page.goto(`${BASE}/how-to-play/`);
    if (!/never steals/.test(await page.textContent("main"))) throw new Error("rules page lacks the setup robber rule");
    await page.screenshot({ path: `${OUT}/e2e-how-to-play.png`, fullPage: true });

    log(`sign up and create a ${PLAYERS}-player game`);
    await signUp(page, "host8");
    await page.goto(`${BASE}/lobby/`);
    await page.selectOption("#id_max_players", String(PLAYERS));
    await Promise.all([page.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), page.click("main form.stacked button[type=submit]")]);
    const code = page.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];
    for (let i = 1; i < PLAYERS; i++) {
      await page.selectOption("#bot-level-select", "easy");
      await Promise.all([page.waitForNavigation(), page.click(`form[action$="/bots/add/"] button`)]);
    }
    const colours = await page.$$eval("table.seats .swatch", (s) => s.map((x) => getComputedStyle(x).backgroundColor));
    if (new Set(colours).size !== PLAYERS) throw new Error(`expected ${PLAYERS} distinct colours, saw ${colours}`);
    await page.screenshot({ path: `${OUT}/e2e-big-lobby.png`, fullPage: true });

    log("start");
    await Promise.all([page.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }), page.click(`form[action$="/start/"] button`)]);
    await page.waitForSelector(".hud-guide", { timeout: STEP_TIMEOUT_MS });
    const guide = (await page.textContent(".hud-guide")).trim();
    log("guide:", guide.slice(0, 90));
    if (!/Step 1 of 4/.test(guide)) throw new Error(`guide does not show the first setup step: ${guide}`);
    const land = await page.evaluate(() => window.island.store.board.hexes.filter((h) => h.land).length);
    if (land < 32) throw new Error(`island too small for ${PLAYERS}: ${land} land hexes`);
    await page.screenshot({ path: `${OUT}/e2e-big-guide.png` });

    await page.click(".hud-guide .help-open");
    await page.waitForSelector(".hud-dialog .help-rules");
    await page.screenshot({ path: `${OUT}/e2e-big-help.png` });
    await page.click(".hud-dialog header button");

    log("the same game on a phone: folded score list");
    const phone = await browser.newContext({ ...devices["Pixel 7"], storageState: await desktop.storageState() });
    const mobile = await phone.newPage();
    mobile.on("pageerror", (e) => { console.error("phone page error:", e.message); process.exitCode = 1; });
    await mobile.goto(`${BASE}/play/${code}/`);
    await mobile.waitForSelector(".hud-scores .scores-fold", { timeout: STEP_TIMEOUT_MS });
    const rows = await mobile.$$eval(".hud-scores li", (l) => l.length);
    if (rows > 4) throw new Error(`folded score list shows ${rows} rows`);
    await mobile.screenshot({ path: `${OUT}/e2e-big-phone.png` });
    await mobile.click(".hud-scores .scores-fold");
    const all = await mobile.$$eval(".hud-scores li", (l) => l.length);
    if (all !== PLAYERS) throw new Error(`unfolded score list shows ${all} rows`);
    await mobile.screenshot({ path: `${OUT}/e2e-big-phone-all.png` });
    await phone.close();

    const t0 = Date.now();
    for (;;) {
      const phase = await page.evaluate(() => window.island?.store?.state?.phase);
      if (phase === "finished") break;
      if (Date.now() - t0 > GAME_TIMEOUT_MS) throw new Error("the bots did not finish in time");
      await page.waitForTimeout(1000);
    }
    await page.waitForSelector(".hud-overlay .winner", { timeout: STEP_TIMEOUT_MS });
    log("sees:", (await page.textContent(".hud-overlay .winner")).trim());
    await page.screenshot({ path: `${OUT}/e2e-big-game-over.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await page.screenshot({ path: `${OUT}/e2e-big-failure.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
