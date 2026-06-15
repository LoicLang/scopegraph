// Drives the conversational scopegraph app and captures the new-UI demo screenshots.
// Prereq: server on :8010 with SCOPEGRAPH_CONVERSATIONAL=1 (DeepSeek). node demo.mjs
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const BASE = "http://127.0.0.1:8010";
const OUT = fileURLToPath(new URL("../../assets/demo/", import.meta.url));
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// Decisive cash-back answers so the assistant can reach perimetre_stable.
const ANSWERS = [
  "un programme de cashback : les clients gagnent un pourcentage quand ils paient par carte chez nos commerçants partenaires",
  "oui, ça se déclenche automatiquement au paiement par carte en magasin, et aussi sur les TPE des partenaires",
  "les clients suivent leur cagnotte sur l'application mobile ; aucun crédit, c'est de la pure fidélité",
  "le calcul peut être différé, une fois par jour la nuit",
  "budget 500k€, lancement dans 6 mois, objectif réduire l'attrition",
  "oui c'est bien ça",
  "je vous laisse cadrer le reste",
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1720, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
const shot = (name) => page.screenshot({ path: OUT + name + ".png" });
const challenged = () => page.locator("#closebadge").isVisible();

async function clickSend() {
  await page.locator('form button:has-text("Envoyer")').click();
}
async function turn(text) {
  await page.locator("form textarea").fill(text);
  const resp = page.waitForResponse((r) => r.url().includes("/message") && r.request().method() === "POST",
    { timeout: 180000 });
  await clickSend();
  await resp;
  await wait(1600); // let Cytoscape + Alpine settle
}

await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 15000 });
console.log("session ready");

// Turn 1: capture the « thinking » indicator while the request is in flight.
await page.locator("form textarea").fill(ANSWERS[0]);
const resp1 = page.waitForResponse((r) => r.url().includes("/message"), { timeout: 180000 });
await clickSend();
await page.locator(".thinking").waitFor({ state: "visible", timeout: 8000 });
await shot("01-thinking");
console.log("01 thinking-indicator captured");
await resp1;
await wait(1600);
await shot("02-map-exclusions");
console.log("02 map + woven question + exclusions captured");

// Drive to the challenge (perimetre_stable → #closebadge appears).
let i = 1;
while (!(await challenged()) && i < ANSWERS.length) {
  await turn(ANSWERS[i]);
  console.log(`  turn ${i + 1} sent — challenged=${await challenged()}`);
  i++;
}
await wait(1500);
await shot("03-challenge-closebadge");
console.log("03 challenge + close badge captured — challenged=", await challenged());

// Accept all grounded cards → the EDB fills with sourced entries.
for (let k = 0; k < 40; k++) {
  const btn = page.locator('.card .actions button:has-text("Accepter")').first();
  if ((await btn.count()) === 0) break;
  await btn.scrollIntoViewIfNeeded();
  const resp = page.waitForResponse((r) => r.url().includes("/proposal"), { timeout: 60000 });
  await btn.click();
  await resp;
  await wait(250);
}
await wait(1200);
await shot("04-edb-grounded");
console.log("04 EDB filled with accepted entries captured");

await browser.close();
console.log("done");
