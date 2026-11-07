// One person against computer players: the host adds two bots in the lobby, starts,
// and does nothing; the bots must walk, build and finish the game on the real servers.
// Run through e2e/run.py. Usage: node e2e/bots.cjs BASE_URL OUT_DIR
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const STEP_TIMEOUT_MS = 60_000;
const GAME_TIMEOUT_MS = 240_000;

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[bots]", ...a);

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

async function addBot(page, level) {
  await page.selectOption("#bot-level-select", level);
  await Promise.all([page.waitForNavigation(), page.click(`form[action$="/bots/add/"] button`)]);
}

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  page.on("pageerror", (e) => { console.error("page error:", e.message); process.exitCode = 1; });
  try {
    log("sign up and create a three-player game");
    await signUp(page, "solo");
    await page.goto(`${BASE}/lobby/`);
    await page.selectOption("#id_max_players", "3");
    await Promise.all([page.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), page.click("main form.stacked button[type=submit]")]);
    const code = page.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];

    log("add a hard and an easy bot, remove one and add it back");
    await addBot(page, "hard");
    await addBot(page, "easy");
    if (await page.locator(`form[action$="/bots/add/"]`).count()) throw new Error("add-bot form shown in a full game");
    await Promise.all([page.waitForNavigation(), page.locator(`form[action$="/bots/remove/"] button`).last().click()]);
    await addBot(page, "easy");
    const badges = await page.$$eval(".badge.bot", (bs) => bs.map((b) => b.textContent.trim()));
    if (badges.length !== 2) throw new Error(`expected two bots, saw ${badges}`);
    log("bots:", badges.join(", "));
    await page.screenshot({ path: `${OUT}/e2e-bots-lobby.png` });

    log("start; the bots play while the person watches");
    await Promise.all([page.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }), page.click(`form[action$="/start/"] button`)]);
    const progress = () => page.evaluate(() => {
      const s = window.island?.store?.state;
      if (!s) return null;
      return { winner: s.winner, phase: s.phase, roll: s.last_roll,
               pts: s.players.map((p) => `${p.name}:${p.points ?? 0}`).join(" "), buildings: s.buildings?.length ?? 0 };
    });
    const t0 = Date.now();
    let shot = false;
    for (;;) {
      const p = await progress();
      if (p && p.roll && !shot) { log("dice rolling:", p.pts); await page.screenshot({ path: `${OUT}/e2e-bots-running.png` }); shot = true; }
      if (p && p.phase === "finished") { log("finished:", p.pts); break; }
      if (Date.now() - t0 > GAME_TIMEOUT_MS) throw new Error(`bots did not finish in time: ${JSON.stringify(p)}`);
      await page.waitForTimeout(500);
    }
    await page.waitForSelector(".hud-overlay .winner", { timeout: STEP_TIMEOUT_MS });
    const winner = (await page.textContent(".hud-overlay .winner")).trim();
    log("sees:", winner);
    if (!/\(bot\)/.test(winner)) throw new Error(`expected a bot to win, got: ${winner}`);
    await page.screenshot({ path: `${OUT}/e2e-bots-game-over.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await page.screenshot({ path: `${OUT}/e2e-bots-failure.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
