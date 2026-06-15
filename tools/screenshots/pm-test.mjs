// Couche 2 E2E: Claude (project manager) drives the conversational app end-to-end
// with DeepSeek as the brain. Asserts the full flow runs and captures any JS/network
// error. Prereq: server on :8010 with SCOPEGRAPH_CONVERSATIONAL=1 + DeepSeek.
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const BASE = "http://127.0.0.1:8010";
const OUT = fileURLToPath(new URL("../../assets/pm-test/", import.meta.url));
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// PM scenario: SEPA instant credit transfer in the online-banking app.
// Decisive answers that explicitly exclude card/POS/credit → should trigger AI exclusions.
const ANSWERS = [
  "On veut ajouter le virement instantané SEPA dans notre application de banque en ligne, pour que les clients particuliers envoient de l'argent en moins de 10 secondes 24/7",
  "Oui, c'est uniquement du virement compte à compte via les rails SEPA Instant ; pas de paiement par carte, pas de TPE, pas de crédit",
  "L'authentification forte DSP2 s'applique à chaque virement ; on réutilise le dispositif SCA existant de l'app",
  "Les clients initient et suivent leurs virements dans l'app mobile et web ; les conseillers n'interviennent pas",
  "Budget 400k€, mise en production dans 5 mois, objectif réduire les délais de virement et l'attrition",
  "Oui c'est exactement le périmètre",
  "Je vous laisse cadrer le reste",
];

const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1720, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();

page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => pageErrors.push(String(e)));
page.on("response", (r) => {
  if (r.url().includes("/api/") && r.status() >= 400) {
    failedRequests.push(`${r.status()} ${r.request().method()} ${r.url()}`);
  }
});

const shot = (name) => page.screenshot({ path: OUT + name + ".png" });
const challenged = () => page.locator("#closebadge").isVisible();

async function clickSend() {
  await page.locator('form button:has-text("Envoyer")').click();
}
async function turn(text) {
  await page.locator("form textarea").fill(text);
  const respP = page.waitForResponse(
    (r) => r.url().includes("/message") && r.request().method() === "POST",
    { timeout: 180000 }
  );
  await clickSend();
  const resp = await respP;
  let body = null;
  try { body = await resp.json(); } catch { /* non-JSON */ }
  await wait(1600); // let Cytoscape + Alpine settle
  return body;
}

const summary = { turns: [], challenged: false, cardsSeen: 0, cardsAccepted: 0,
                  edbFilled: 0, rejectedNodes: 0, closeReason: null, missingText: null };

// 1) Session boots: the bot greeting must appear.
await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 20000 });
await shot("01-greeting");
console.log("[OK] session ready — greeting visible");

// 2) Drive the conversation as PM until the challenge fires (or answers run out).
let mapEverRendered = false;
for (let i = 0; i < ANSWERS.length; i++) {
  const body = await turn(ANSWERS[i]);
  const nodes = body && body.map && body.map.nodes ? body.map.nodes.length : 0;
  const state = body ? body.state : "?";
  if (nodes > 0) mapEverRendered = true;
  summary.turns.push({ n: i + 1, state, mapNodes: nodes, closeReason: body && body.close_reason });
  console.log(`[turn ${i + 1}] state=${state} mapNodes=${nodes} close=${body && body.close_reason}`);
  if (i === 0) await shot("02-after-subject");
  if (await challenged()) { summary.challenged = true; break; }
}

await wait(1200);
summary.closeReason = await page.evaluate(() => {
  const el = document.querySelector("#closebadge");
  return el ? el.textContent.trim() : null;
});
await shot("03-challenge");
console.log(`[challenge] reached=${summary.challenged} closeBadge="${summary.closeReason}"`);

// 3) Accept every grounded card → the EDB should fill with sourced entries.
summary.cardsSeen = await page.locator(".card").count();
for (let k = 0; k < 40; k++) {
  const btn = page.locator('.card .actions button:has-text("Accepter")').first();
  if ((await btn.count()) === 0) break;
  await btn.scrollIntoViewIfNeeded();
  const respP = page.waitForResponse((r) => r.url().includes("/proposal"), { timeout: 60000 });
  await btn.click();
  await respP;
  summary.cardsAccepted++;
  await wait(300);
}
await wait(1200);

// 4) Read final EDB + exclusions state from the DOM.
summary.edbFilled = await page.locator("#edb .entry:not(.muted)").count();
summary.rejectedNodes = await page.locator("#rejected .row").count();
summary.missingText = await page.evaluate(() => {
  const b = document.querySelector("#edb .badge");
  return b ? b.textContent.trim() : null;
});
await shot("04-edb-grounded");
console.log(`[edb] filledEntries=${summary.edbFilled} rejectedNodes=${summary.rejectedNodes} badge="${summary.missingText}"`);

await browser.close();

// 5) Verdict.
summary.consoleErrors = consoleErrors;
summary.pageErrors = pageErrors;
summary.failedRequests = failedRequests;
console.log("\n=== SUMMARY ===");
console.log(JSON.stringify(summary, null, 2));

const hardFailures = [];
if (!mapEverRendered) hardFailures.push("map never rendered");
if (pageErrors.length) hardFailures.push(`${pageErrors.length} page error(s)`);
if (consoleErrors.length) hardFailures.push(`${consoleErrors.length} console error(s)`);
if (failedRequests.length) hardFailures.push(`${failedRequests.length} failed API request(s)`);
if (summary.challenged && summary.cardsAccepted === 0) hardFailures.push("challenged but no card accepted");
if (summary.challenged && summary.edbFilled === 0) hardFailures.push("challenge done but EDB empty");

if (hardFailures.length) {
  console.log("\n[FAIL] " + hardFailures.join("; "));
  process.exit(1);
}
console.log("\n[PASS] full conversational flow ran clean");
