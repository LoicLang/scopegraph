// Couche 2 E2E for the EDB-synthesis UX: proposals validate in the EDB pane (not the
// chat), batch "Tout valider" works, user entries are reformulated & single-per-section,
// the statement card lands under « challenge ». Prereq: server :8011, conversational+DeepSeek.
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const BASE = "http://127.0.0.1:8011";
const OUT = fileURLToPath(new URL("../../assets/pm-edb/", import.meta.url));
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const ANSWERS = [
  "On veut ajouter le virement instantané SEPA dans notre application de banque en ligne, pour que les clients particuliers envoient de l'argent en moins de 10 secondes 24/7",
  "Oui, c'est uniquement du virement compte à compte via les rails SEPA Instant ; pas de paiement par carte, pas de TPE, pas de crédit",
  "L'authentification forte DSP2 s'applique à chaque virement ; on réutilise le dispositif SCA existant de l'app",
  "Les clients initient et suivent leurs virements dans l'app mobile et web ; les conseillers n'interviennent pas",
  "Budget 400k€, mise en production dans 5 mois, objectif réduire les délais de virement et l'attrition",
  "Oui c'est exactement le périmètre",
];

const consoleErrors = [], pageErrors = [], failedRequests = [];
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1720, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => pageErrors.push(String(e)));
page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) failedRequests.push(`${r.status()} ${r.url()}`); });

const shot = (n) => page.screenshot({ path: OUT + n + ".png" });
const challenged = () => page.locator("#closebadge").isVisible();
async function turn(text) {
  const ta = page.locator("form textarea");
  await ta.fill(text);
  // ensure x-model="draft" has actually picked up the value before submitting (avoids a
  // first-turn race that posts an empty body the server rightly 422s on min_length=1).
  await page.waitForFunction((t) => document.querySelector("form textarea")?.value === t, text, { timeout: 5000 });
  const p = page.waitForResponse((r) => r.url().includes("/message") && r.request().method() === "POST", { timeout: 180000 });
  await page.locator('form button:has-text("Envoyer")').click();
  await p; await wait(1500);
}

const S = {};
// wait for the session to be created (sessionId set) before typing the first turn.
const sessP = page.waitForResponse((r) => r.url().endsWith("/api/session") && r.request().method() === "POST", { timeout: 20000 });
await page.goto(BASE);
await sessP;
await page.locator(".bot").first().waitFor({ timeout: 20000 });
for (let i = 0; i < ANSWERS.length && !(await challenged()); i++) {
  await turn(ANSWERS[i]);
  console.log(`[turn ${i + 1}] challenged=${await challenged()}`);
}
await wait(1200);
S.challenged = await challenged();

// --- The new UX invariants, BEFORE validation ---
S.propsInEdbPane = await page.locator("#edb .prop").count();
S.cardsFloodingChat = await page.locator("#chat .card, #messages .card").count();  // must be 0
S.handoffVisible = await page.locator(".handoff").isVisible().catch(() => false);
S.validateAllVisible = await page.locator(".validate-all").isVisible().catch(() => false);
// statement card (#4) exists ONLY when the challenge statement was flagged/quarantined;
// a clean statement is written straight to the challenge EDB section (no card). When a
// statement card DOES exist, it must be routed under « challenge ».
S.statement = await page.evaluate(() => {
  const tag = "Énoncé de défi";
  const all = [...document.querySelectorAll("#edb .prop .prop-tag")].filter((t) => t.textContent.includes(tag)).length;
  const secs = [...document.querySelectorAll("#edb .section")];
  const ch = secs.find((s) => s.querySelector("h3")?.textContent?.includes("Challenge"));
  const underChallenge = ch ? [...ch.querySelectorAll(".prop .prop-tag")].filter((t) => t.textContent.includes(tag)).length : 0;
  return { all, underChallenge };
});
S.sampleProps = await page.locator("#edb .prop .prop-text").allInnerTexts().then((a) => a.slice(0, 4));
await shot("01-proposals-in-edb-pane");
console.log(`[before] props=${S.propsInEdbPane} chatCards=${S.cardsFloodingChat} handoff=${S.handoffVisible} validateAll=${S.validateAllVisible} statementCards=${S.statement.all} underChallenge=${S.statement.underChallenge}`);

// --- Batch validate everything ---
if (S.validateAllVisible) {
  const n = S.propsInEdbPane;
  const waiters = page.waitForResponse((r) => r.url().includes("/proposal"), { timeout: 60000 });
  await page.locator(".validate-all").click();
  await waiters;
  // wait until all props are consumed
  for (let k = 0; k < 60 && (await page.locator("#edb .prop").count()) > 0; k++) await wait(400);
}
await wait(1000);

// --- AFTER validation ---
S.propsRemaining = await page.locator("#edb .prop").count();          // expect 0
S.edbFilled = await page.locator("#edb .entry:not(.muted)").count();  // expect > 0
S.challengeFilled = await page.evaluate(() => {
  const secs = [...document.querySelectorAll("#edb .section")];
  const ch = secs.find((s) => s.querySelector("h3")?.textContent?.includes("Challenge"));
  return ch ? ch.querySelectorAll(".entry").length : -1;
});
// single user entry per section (the synthesis invariant)
S.sectionsWithMultipleUserEntries = await page.evaluate(() => {
  let bad = 0;
  for (const s of document.querySelectorAll("#edb .section")) {
    if (s.querySelectorAll(".entry .src.user").length > 1) bad++;
  }
  return bad;
});
S.userEntrySample = await page.evaluate(() => {
  const e = [...document.querySelectorAll("#edb .entry")].find((x) => x.querySelector(".src.user"));
  return e ? e.textContent.replace(/\s+/g, " ").trim().slice(0, 200) : null;
});
await shot("02-edb-validated");
console.log(`[after] propsRemaining=${S.propsRemaining} edbFilled=${S.edbFilled} challengeEntries=${S.challengeFilled} multiUserSections=${S.sectionsWithMultipleUserEntries}`);

await browser.close();
S.consoleErrors = consoleErrors; S.pageErrors = pageErrors; S.failedRequests = failedRequests;
console.log("\n=== SUMMARY ===\n" + JSON.stringify(S, null, 2));

const fail = [];
if (!S.challenged) fail.push("challenge not reached");
if (S.cardsFloodingChat !== 0) fail.push(`${S.cardsFloodingChat} cards still in chat (should be in EDB pane)`);
if (S.propsInEdbPane === 0) fail.push("no proposals in EDB pane");
if (S.statement.all > 0 && S.statement.underChallenge !== S.statement.all)
  fail.push("a statement card exists but is not routed under « challenge »");
if (S.propsRemaining !== 0) fail.push(`${S.propsRemaining} proposals left after Tout valider`);
if (S.edbFilled === 0) fail.push("EDB empty after validation");
if (S.challengeFilled < 1) fail.push("challenge section empty after validation");
if (S.sectionsWithMultipleUserEntries !== 0) fail.push(`${S.sectionsWithMultipleUserEntries} section(s) with >1 user entry (synthesis broken)`);
if (pageErrors.length) fail.push(`${pageErrors.length} page error(s)`);
if (consoleErrors.length) fail.push(`${consoleErrors.length} console error(s)`);
if (failedRequests.length) fail.push(`${failedRequests.length} failed API request(s)`);

if (fail.length) { console.log("\n[FAIL] " + fail.join("; ")); process.exit(1); }
console.log("\n[PASS] new EDB-pane validation UX works clean");
