// Live fog with hidden numbers: a person opens a settings-code link, plays now
// against two bots, and must see only the land around their own settler while the
// bots build out of sight; other players' settlers show only while in sight, and
// land seen before but out of sight is veiled. The bots finish the game and the fog
// lifts. Run through e2e/run.py.
// Usage: node e2e/fog.cjs BASE_URL OUT_DIR
const { chromium } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const GAME_TIMEOUT_MS = 240_000;
// classic with visibility.map = live_fog and hidden_numbers (engine.settings.encode_share_code)
const CODE = "classic.1.eNqrVirLLM5MyszJLKlUsqpWyshMSUnNi88rzU1KLSpWsiopKk3VUcpNLFCyUsrJLEuNT8tPV6qtBQA94hQz";

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[fog]", ...a);

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
    log("sign up, open the code link and play now against bots");
    await signUp(page, "scout");
    await page.goto(`${BASE}/lobby/?config=${encodeURIComponent(CODE)}#create-game`);
    if (!(await page.isVisible("#code-box"))) throw new Error("the settings code box is not shown for a code link");
    await Promise.all([page.waitForURL(/\/play\/[A-Z0-9]+\/$/, { timeout: 60_000 }), page.click('button[name="play_bots"]')]);
    await page.waitForFunction(() => window.island?.store?.state && window.island?.store?.board);

    const view = () => page.evaluate(() => {
      const { board, state } = window.island.store;
      const hexes = board.hexes.filter((h) => h);
      const seen = new Set(hexes.map((h) => h.id));
      const vseen = new Set(board.vertices.filter((v) => v).map((v) => v.id));
      return {
        partial: !!board.partial, hexes: hexes.length,
        tokens: hexes.filter((h) => h.land && h.token !== null).length,
        hiddenTokens: hexes.filter((h) => h.land && h.token === null && h.terrain && h.terrain !== "desert").length,
        othersUnseen: state.buildings.filter((b) => b.seat !== state.viewer && !vseen.has(b.vertex)).length,
        settlersOutOfSight: state.phase === "finished" ? 0 : state.settlers.filter((s) => s.seat !== state.viewer
          && !(board.vertices[s.vertex]?.hexes ?? []).some((h) => (state.visibility?.in_sight ?? []).includes(h))).length,
        robberUnseen: state.robber !== null && !seen.has(state.robber),
        phase: state.phase, others: state.buildings.filter((b) => b.seat !== state.viewer).length,
        seen: (state.visibility?.seen ?? []).length,
      };
    });
    const first = await view();
    log("start:", JSON.stringify(first));
    if (!first.partial) throw new Error("the board is not partial under Growing sight");
    if (first.hexes > 10) throw new Error(`saw ${first.hexes} hexes at the start`);
    if (first.tokens !== 0) throw new Error("number tokens shown before any building");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/e2e-fog-start.png` });

    log("walk the settler inland: the land around it is revealed");
    await page.click("canvas", { position: { x: 1200, y: 600 } }).catch(() => {});
    for (const key of ["w", "a", "s", "d", "w", "a", "w", "d"]) {
      await page.keyboard.press(key);
      await page.waitForTimeout(450);
    }
    const walked = await view();
    log("after walking:", JSON.stringify(walked));
    if (walked.hexes <= first.hexes && walked.phase !== "finished") throw new Error("walking revealed no land");
    await page.screenshot({ path: `${OUT}/e2e-fog-walked.png` });

    log("the bots play out of sight until the end");
    const t0 = Date.now();
    for (;;) {
      const v = await view();
      if (v.othersUnseen || v.robberUnseen || v.settlersOutOfSight) throw new Error(`told about pieces out of sight: ${JSON.stringify(v)}`);
      if (v.phase === "finished") {
        log("finished:", JSON.stringify(v));
        if (v.partial) throw new Error("the fog did not lift at the end");
        break;
      }
      if (Date.now() - t0 > GAME_TIMEOUT_MS) throw new Error(`bots did not finish in time: ${JSON.stringify(v)}`);
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: `${OUT}/e2e-fog-end.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await page.screenshot({ path: `${OUT}/e2e-fog-failure.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
