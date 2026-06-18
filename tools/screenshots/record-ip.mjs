// Final demo recording — a project manager scoping a *virement instantané* project.
// Storyline emphasises PART 1: the graph focusing itself through the assistant's
// pertinent questions (SCA, plafonds) and the visible pruning of off-scope domains,
// up to the stabilised perimeter; then a short payoff (Tout valider → grounded dossier).
//
// Smoothness: run this TWICE against a server started with SCOPEGRAPH_CACHE_DIR set.
// Pass 1 (live) primes every LLM call into the disk cache; pass 2 replays instantly,
// so the model's "thinking" time is gone and the capture is fluid — no post-edit needed.
// Prereq: server on :8010, SCOPEGRAPH_CONVERSATIONAL=1, SCOPEGRAPH_CACHE_DIR=<dir>, DeepSeek.
import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { mkdirSync, readdirSync, rmSync } from "fs";

const BASE = "http://127.0.0.1:8010";
const OUT = fileURLToPath(new URL("../../assets/demo/", import.meta.url));
const RAW = OUT + "_rec/";
mkdirSync(RAW, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// Each answer genuinely responds to the assistant's actual (dynamic) question — captured
// from an adaptive say.py interview so the conversation reads coherently on screen, never
// a scripted reply that lands beside the question. Kept verbatim so the cache replays it.
const ANSWERS = [
  "Bonjour. Je veux cadrer un nouveau projet : permettre à nos clients particuliers d'émettre des virements instantanés depuis l'application mobile, y compris l'ajout d'un nouveau bénéficiaire directement en ligne.",
  "Oui aux deux. La SCA est systématique à chaque ajout d'un nouveau bénéficiaire, c'est une obligation réglementaire. Et la vérification des sanctions LCB-FT doit être intégrée directement dans le parcours, de façon synchrone et bloquante à la création du bénéficiaire — pas seulement en back-office.",
  "Le projet couvre l'ajout, la consultation et la modification des bénéficiaires, plus l'émission et la réception de virements instantanés ; la suppression peut attendre une V2. On veut aussi des plafonds paramétrables sur le virement instantané. En revanche, tout ce qui est carte bancaire, TPE et crédit est hors périmètre.",
  "oui c'est bien ça",
];

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  recordVideo: { dir: RAW, size: { width: 1600, height: 900 } },
});
const page = await ctx.newPage();
const shot = (n) => page.screenshot({ path: OUT + n + ".png" });
const challenged = () => page.locator("#closebadge").isVisible();
const excluded = () => page.locator("#rejected").isVisible();

async function type(text) {
  const ta = page.locator("form textarea");
  await ta.click();
  await ta.pressSequentially(text, { delay: 16 });   // deliberate, readable typing
  await wait(280);
}
async function send() {
  const resp = page.waitForResponse(
    (r) => r.url().includes("/message") && r.request().method() === "POST", { timeout: 180000 });
  await page.locator('form button:has-text("Envoyer")').click();
  await resp;                                          // instant on the cached pass
}

await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 15000 });
await wait(1100);                                      // settle on the empty canvas

// — Turn 1: the PM states the project; the Context Map focuses on the right domains —
await type(ANSWERS[0]);
const r1 = page.waitForResponse((r) => r.url().includes("/message"), { timeout: 180000 });
await page.locator('form button:has-text("Envoyer")').click();
try { await page.locator(".thinking").waitFor({ state: "visible", timeout: 4000 }); await shot("ip-final-01-thinking"); } catch {}
await r1;
await wait(2400);                                      // let the map build + read the woven question
await shot("ip-final-02-map");

// — Drive the pertinent-questions loop; linger when the graph prunes off-scope nodes —
let i = 1;
while (!(await challenged()) && i < ANSWERS.length) {
  await type(ANSWERS[i]);
  await send();
  await wait(1700);                                    // read the assistant's pertinent question
  if (await excluded()) { await wait(1500); }          // show the focus: excluded domains panel
  i++;
}
await wait(1600);
await shot("ip-final-03-perimetre");                   // stabilised perimeter + close badge

// — Short payoff: validate the grounded proposals; the dossier fills in place —
const all = page.locator("#edb .validate-all");
if (await all.count()) {
  await all.scrollIntoViewIfNeeded();
  await all.click();
  for (let k = 0; k < 60 && (await page.locator("#edb .prop").count()) > 0; k++) await wait(350);
}
await wait(2600);                                      // linger on the grounded dossier
await shot("ip-final-04-dossier");

const video = page.video();
await ctx.close();
await video.saveAs(OUT + "demo-cadrage-final.webm");
await browser.close();
// tidy the raw recordings so only the final webm remains in assets/demo
try { for (const f of readdirSync(RAW)) rmSync(RAW + f); rmSync(RAW, { recursive: true }); } catch {}
console.log("video saved:", OUT + "demo-cadrage-final.webm");
