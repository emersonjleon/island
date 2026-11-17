// The players' chat: two people talk in the waiting room (a desktop and a phone),
// start the game and keep talking in it; the phone sees the unread badge and the
// preview, opens the panel, answers with a quick phrase and a resource icon, in
// portrait and landscape. Run through e2e/run.py. Usage: node e2e/chat.cjs BASE_URL OUT_DIR
const { chromium, devices } = require("playwright");

const BASE = process.argv[2] || "http://127.0.0.1:8765";
const OUT = process.argv[3] || ".";
const PASSWORD = "Zx9-long-pass!";
const STEP_TIMEOUT_MS = 30_000;
const PHONE = devices["Pixel 7"];

// The other e2e scripts share the database, so names get a suffix of their own.
const TAG = Date.now().toString(36).slice(-4);
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), "[chat]", ...a);

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

async function spanish(page) {
  await Promise.all([page.waitForNavigation(), page.selectOption("#language-select", "es")]);
}

async function expectLine(page, scope, text) {
  await page.locator(`${scope} .chat-lines li`, { hasText: text }).first().waitFor({ timeout: STEP_TIMEOUT_MS });
}

async function say(page, scope, text) {
  await page.fill(`${scope} .chat-form input`, text);
  await page.press(`${scope} .chat-form input`, "Enter");
}

(async () => {
  const browser = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {});
  const desk = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  const phoneCtx = await browser.newContext({ ...PHONE });
  const phone = await phoneCtx.newPage();
  for (const [who, p] of [["desk", desk], ["phone", phone]]) {
    p.on("pageerror", (e) => { console.error(`${who} page error:`, e.message); process.exitCode = 1; });
  }
  try {
    log("sign up; the desktop creates a two-player game; the phone joins");
    await signUp(desk, `ana${TAG}`);
    await spanish(desk);
    await signUp(phone, `bo${TAG}`);
    await spanish(phone);
    await desk.goto(`${BASE}/lobby/`);
    await desk.selectOption("#id_max_players", "2");
    await Promise.all([desk.waitForURL(/\/lobby\/[A-Z0-9]+\/$/), desk.click("main form.stacked button[type=submit]")]);
    const code = desk.url().match(/\/lobby\/([A-Z0-9]+)\/$/)[1];
    await phone.goto(`${BASE}/lobby/${code}/`);
    await Promise.all([phone.waitForNavigation(), phone.click(`form[action$="/join/"] button`)]);

    log("talk in the waiting room");
    await desk.waitForSelector("#lobby-chat .chat-form input", { timeout: STEP_TIMEOUT_MS });
    await phone.waitForSelector("#lobby-chat .chat-form input", { timeout: STEP_TIMEOUT_MS });
    await say(desk, "#lobby-chat", "¡Hola! ¿Listo para jugar?");
    await expectLine(phone, "#lobby-chat", "¿Listo para jugar?");
    await say(phone, "#lobby-chat", "Sí, dame un segundo");
    await expectLine(desk, "#lobby-chat", "dame un segundo");
    await Promise.all([phone.waitForNavigation(), phone.click(`form[action$="/ready/"] button`)]);
    await expectLine(phone, "#lobby-chat", "dame un segundo");  // the chat survives the page reload
    await phone.locator(".lobby-chat").scrollIntoViewIfNeeded();
    await phone.screenshot({ path: `${OUT}/chat-lobby-phone.png` });
    await desk.screenshot({ path: `${OUT}/chat-lobby-desktop.png`, fullPage: true });

    log("start; the conversation carries into the game");
    await desk.waitForSelector(`form[action$="/start/"] button:not([disabled])`, { timeout: STEP_TIMEOUT_MS });
    await Promise.all([
      desk.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      phone.waitForURL(`**/play/${code}/`, { timeout: STEP_TIMEOUT_MS }),
      desk.click(`form[action$="/start/"] button`),
    ]);
    await desk.waitForSelector(".chat-toggle", { timeout: STEP_TIMEOUT_MS });
    await phone.waitForSelector(".chat-toggle", { timeout: STEP_TIMEOUT_MS });
    await desk.click(".chat-toggle");
    await expectLine(desk, ".chat-panel", "¿Listo para jugar?");

    log("a trade offer in words, with resource icons");
    await desk.fill(".chat-panel .chat-form input", "¿Alguien me cambia 2 ");
    await desk.click(".chat-panel .chat-res-btn.res-lumber");
    await desk.type(".chat-panel .chat-form input", " por 1 ");
    await desk.click(".chat-panel .chat-res-btn.res-grain");
    await desk.press(".chat-panel .chat-form input", "Enter");
    await expectLine(desk, ".chat-panel", "me cambia");
    const icons = await desk.locator(".chat-panel .chat-lines li").last().locator(".chat-res").count();
    if (icons !== 2) throw new Error(`expected two resource icons in the line, saw ${icons}`);

    log("the phone gets a badge and a preview");
    await phone.waitForSelector(".chat-badge", { timeout: STEP_TIMEOUT_MS });
    await phone.waitForSelector(".chat-peek", { timeout: STEP_TIMEOUT_MS });
    await phone.screenshot({ path: `${OUT}/chat-game-phone-preview.png` });
    await phone.click(".chat-toggle");
    await phone.waitForSelector(".chat-panel", { timeout: STEP_TIMEOUT_MS });
    if (await phone.locator(".chat-badge").count()) throw new Error("badge still shown with the panel open");
    await phone.click(".chat-panel .chat-quick button >> nth=1");  // "¡Trato hecho!"
    await expectLine(desk, ".chat-panel", "Trato hecho");
    await phone.screenshot({ path: `${OUT}/chat-game-phone-portrait.png` });
    await desk.screenshot({ path: `${OUT}/chat-game-desktop.png` });

    log("the trade dialog and the chat side by side on the desktop");
    await desk.click(".trade-open");
    await desk.waitForSelector(".hud-dialog", { timeout: STEP_TIMEOUT_MS });
    await say(desk, ".chat-panel", "Te mando la oferta");
    await expectLine(phone, ".chat-panel", "Te mando la oferta");
    await desk.screenshot({ path: `${OUT}/chat-game-desktop-trade.png` });

    log("landscape phone");
    await phone.setViewportSize({ width: PHONE.viewport.height, height: PHONE.viewport.width });
    await phone.waitForTimeout(600);
    await phone.screenshot({ path: `${OUT}/chat-game-phone-landscape.png` });
    await phone.click(".chat-panel .chat-close");
    if (await phone.locator(".chat-panel").count()) throw new Error("panel still open after closing");
    await phone.screenshot({ path: `${OUT}/chat-game-phone-landscape-closed.png` });
    log("PASS");
  } catch (err) {
    console.error("FAIL:", err.message);
    await desk.screenshot({ path: `${OUT}/chat-failure-desktop.png` }).catch(() => {});
    await phone.screenshot({ path: `${OUT}/chat-failure-phone.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
