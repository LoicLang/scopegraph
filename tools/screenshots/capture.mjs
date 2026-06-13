// Drives the live scopegraph app and captures the README screenshots.
// Prereq: server running on :8000 with SCOPEGRAPH_LLM_PROVIDER=mistral.
//   npm install && node capture.mjs
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const OUT = new URL("../../assets/screenshots/", import.meta.url).pathname;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// A real PM who knows the business but not the SI. This exact sequence drives the
// cash-back scenario to a rich challenge (28-node map, 12 grounded claims).
const ANSWERS = [
  "En magasin chez nos partenaires ; objectif ramener du volume carte, pilote avant fin d'année.",
  "Oui, paiements carte en magasin et terminaux concernés.",
  "Je ne sais pas la technique, à vous de me dire.",
  "Dites-moi ce qui est impacté.",
  "Clients particuliers porteurs de carte ; porté par la Monétique.",
  "Je ne sais pas.",
  "Je ne sais pas.",
];

const page = await (async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1680, height: 1000 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  p._browser = browser;
  return p;
})();

async function send(text) {
  const input = page.locator('form input');
  await input.fill(text);
  const resp = page.waitForResponse(
    (r) => r.url().includes("/message") && r.request().method() === "POST",
    { timeout: 180000 },
  );
  await page.locator('form button:has-text("Envoyer")').click();
  await resp;
  await wait(1600); // let Cytoscape layout + Alpine render settle
}

async function acceptAll() {
  for (let i = 0; i < 30; i++) {
    const btn = page.locator('.card .actions button:has-text("Accepter")').first();
    if ((await btn.count()) === 0) break;
    const resp = page.waitForResponse((r) => r.url().includes("/proposal"), { timeout: 60000 });
    await btn.click();
    await resp;
    await wait(300);
  }
  await wait(800);
}

const shot = (name) => page.screenshot({ path: OUT + name + ".png" });
const hasClaim = async () => (await page.locator('.card .kind:has-text("Affirmation")').count()) > 0;
// Reliable "challenge has run" signal: the EDB Challenge section is filled.
const challenged = async () =>
  (await page.locator('#edb .section:has(h3:has-text("Challenge")) .entry:not(.muted)').count()) > 0;

await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 15000 });
console.log("session ready");

await send("Proposer un programme de cash-back lors des paiements chez les commerçants partenaires.");
await shot("01-map-and-interview");
console.log("01 captured — map + woven question + enrichment chips");

await send(ANSWERS[0]);
await acceptAll();
await shot("02-edb-extraction");
console.log("02 captured — EDB filling from a free answer");

// Drive to the challenge WITHOUT accepting mid-flow (matches the API path that yields
// the rich 12-claim challenge — accepting field cards mid-interview is incidental).
let i = 1;
while (!(await challenged()) && i < ANSWERS.length) {
  await send(ANSWERS[i]);
  console.log(`  turn ${i + 1} sent — challenged=${await challenged()} claims=${await hasClaim()}`);
  i++;
}

if (await challenged()) {
  await wait(1500); // let the post-challenge map re-render fully
  const diag = await page.evaluate(() => {
    const cyEl = document.getElementById("cy");
    const r = cyEl.getBoundingClientRect();
    const canvases = cyEl.querySelectorAll("canvas");
    return { w: Math.round(r.width), h: Math.round(r.height), canvases: canvases.length,
             empty: getComputedStyle(document.getElementById("empty")).display };
  });
  console.log("  map diag:", JSON.stringify(diag));
  const claim = page.locator('.card', { has: page.locator('.kind:has-text("Affirmation")') }).first();
  if (await hasClaim()) {
    await claim.scrollIntoViewIfNeeded(); // bring the grounded cards into the chat view
    await wait(500);
  }
  await shot("03-challenge");
  console.log(`03 captured — challenge + map (claims=${await hasClaim()})`);
  if (await hasClaim()) {
    await claim.screenshot({ path: OUT + "03b-claim-provenance.png" });
    console.log("03b captured — a claim card with its node provenance");
  }
  await acceptAll();
  await shot("04-edb-grounded");
  console.log("04 captured — EDB filled with grounded entries");
} else {
  console.log("WARNING: challenge did not fire within the scripted answers");
}

await page._browser.close();
console.log("done");
