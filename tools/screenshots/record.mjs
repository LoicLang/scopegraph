// Records a video of a full conversational scoping run (first message → challenge →
// accepting the grounded cards). Prereq: server on :8010 (SCOPEGRAPH_CONVERSATIONAL=1).
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const BASE = "http://127.0.0.1:8010";
const OUT = fileURLToPath(new URL("../../assets/demo/", import.meta.url));
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const ANSWERS = [
  "un programme de cashback : les clients gagnent un pourcentage quand ils paient par carte chez nos commerçants partenaires",
  "oui, ça se déclenche automatiquement au paiement par carte en magasin",
  "les clients suivent leur cagnotte sur l'application mobile, et il n'y a aucun crédit, c'est de la pure fidélité",
  "oui, ça concerne aussi les terminaux de paiement des partenaires",
  "le calcul peut être différé, une fois par jour la nuit",
  "budget 500k€, lancement dans 6 mois",
  "je vous laisse cadrer le reste",
];

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  recordVideo: { dir: OUT, size: { width: 1600, height: 900 } },
});
const page = await ctx.newPage();
const challenged = () => page.locator("#closebadge").isVisible();

async function turn(text, pause = 1200) {
  const ta = page.locator("form textarea");
  await ta.click();
  await ta.pressSequentially(text, { delay: 9 });    // visible but quick typing
  await wait(250);
  const resp = page.waitForResponse(
    (r) => r.url().includes("/message") && r.request().method() === "POST", { timeout: 180000 });
  await page.locator('form button:has-text("Envoyer")').click();
  await resp;
  await wait(pause);                                  // brief settle so the graph is seen
}

async function acceptAll() {                          // accept every pending card (fills the EDB)
  for (let k = 0; k < 40; k++) {
    const btn = page.locator('.card .actions button:has-text("Accepter")').first();
    if ((await btn.count()) === 0) break;
    await btn.scrollIntoViewIfNeeded();
    const resp = page.waitForResponse((r) => r.url().includes("/proposal"), { timeout: 60000 });
    await btn.click();
    await resp;
    await wait(350);                                  // visible acceptance
  }
}

await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 15000 });
await wait(700);

await turn(ANSWERS[0]);
let i = 1;
while (!(await challenged()) && i < ANSWERS.length) {
  await turn(ANSWERS[i]);
  console.log(`turn ${i + 1} — challenged=${await challenged()}`);
  i++;
}
await wait(1200);
await acceptAll();                                    // accept the grounded claims + EDB entries
await wait(2500);                                     // linger on the filled dossier

const video = page.video();
await ctx.close();
await video.saveAs(OUT + "demo-cadrage.webm");
await browser.close();
console.log("video saved:", OUT + "demo-cadrage.webm");
