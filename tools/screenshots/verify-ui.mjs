// Verifies the redesigned UI: cards must leave the chat and appear as pending
// proposals inside the EDB pane, with batch validation. Prereq: server on :8010
// (SCOPEGRAPH_CONVERSATIONAL=1, DeepSeek). node verify-ui.mjs
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const BASE = "http://127.0.0.1:8010";
const OUT = fileURLToPath(new URL("../../assets/demo/", import.meta.url));
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const ANSWERS = [
  "Bonjour. Je veux cadrer un projet : permettre à nos clients particuliers d'émettre des virements instantanés depuis l'application mobile, avec l'ajout d'un nouveau bénéficiaire en ligne.",
  "Oui, SCA systématique à chaque ajout d'un nouveau bénéficiaire, c'est une obligation réglementaire.",
  "Oui, des plafonds paramétrables par jour et par opération, avec un plafond par défaut prudent. Pas de carte, pas de TPE, aucun crédit.",
  "oui c'est bien ça",
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));
const shot = (n) => page.screenshot({ path: OUT + n + ".png" });
const challenged = () => page.locator("#closebadge").isVisible();

async function turn(text) {
  await page.locator("form textarea").fill(text);
  const resp = page.waitForResponse((r) => r.url().includes("/message") && r.request().method() === "POST",
    { timeout: 180000 });
  await page.locator('form button:has-text("Envoyer")').click();
  await resp;
  await wait(1500);
}

await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 15000 });

let i = 0;
while (!(await challenged()) && i < ANSWERS.length) {
  await turn(ANSWERS[i]);
  console.log(`turn ${i + 1} sent — challenged=${await challenged()}`);
  i++;
}
await wait(1200);

// Assertions on the new layout.
const cardsInChat = await page.locator("#messages .card, #messages .prop").count();
const pendingInEdb = await page.locator("#edb .prop").count();
const badge = (await page.locator("#edb .badge.warn").count())
  ? (await page.locator("#edb .badge.warn").innerText()) : "(none)";
const hasToutValider = await page.locator('#edb .validate-all:has-text("Tout valider")').count();
const hasSectionValidate = await page.locator('#edb .sec-validate').count();
const handoff = await page.locator('#chat .handoff').isVisible().catch(() => false);
console.log("cards left in chat   :", cardsInChat, "(must be 0)");
console.log("pending props in EDB :", pendingInEdb);
console.log("EDB warn badge       :", badge);
console.log("'Tout valider' btn   :", hasToutValider);
console.log("'Valider section' btns:", hasSectionValidate);
console.log("chat hand-off hint   :", handoff);
await shot("ui-01-pending-in-edb");

// Exercise batch validation.
if (hasToutValider) {
  const before = await page.locator("#edb .prop").count();
  await page.locator('#edb .validate-all').click();
  await wait(4000);
  const after = await page.locator("#edb .prop").count();
  const entries = await page.locator("#edb .entry").count();
  console.log(`Tout valider: pending ${before} -> ${after}; filled entries now ${entries}`);
  await shot("ui-02-edb-validated");
}

console.log("CONSOLE ERRORS:", errors.length ? errors : "none");
await browser.close();
