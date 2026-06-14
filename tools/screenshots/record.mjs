// Records a cinematic demo video of the live scopegraph app (Playwright + CSS motion).
// Prereq: server on :8000 with SCOPEGRAPH_CACHE_DIR warm (instant replays → no dead air).
//   node record.mjs   →   videos/*.webm   (then assemble with ffmpeg)
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const SIZE = { width: 1440, height: 900 };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const ANSWERS = [
  "En magasin chez nos partenaires ; objectif ramener du volume carte, pilote avant fin d'année.",
  "Oui, paiements carte en magasin et terminaux concernés.",
  "Je ne sais pas la technique, à vous de me dire.",
  "Dites-moi ce qui est impacté.",
  "Clients particuliers porteurs de carte ; porté par la Monétique.",
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: "videos", size: SIZE } });
const page = await ctx.newPage();

async function chrome() {
  await page.addStyleTag({
    content: `
      body { overflow: hidden; }
      main { transition: transform 1.1s cubic-bezier(.6,.02,.2,1); will-change: transform; }
      #democursor { position: fixed; width: 22px; height: 22px; border-radius: 50%;
        background: rgba(29,111,209,.35); border: 2px solid #1d6fd1; z-index: 99999;
        pointer-events: none; transform: translate(-50%,-50%);
        transition: left .6s cubic-bezier(.22,1,.36,1), top .6s cubic-bezier(.22,1,.36,1), width .15s, height .15s; }
    `,
  });
  await page.evaluate(() => {
    const c = document.createElement("div");
    c.id = "democursor";
    c.style.left = "50%";
    c.style.top = "92%";
    document.body.appendChild(c);
  });
}
const moveTo = async (sel) => {
  const box = await page.locator(sel).first().boundingBox();
  if (!box) return;
  await page.evaluate(
    ([x, y]) => {
      const c = document.getElementById("democursor");
      c.style.left = x + "px";
      c.style.top = y + "px";
    },
    [box.x + box.width / 2, box.y + box.height / 2],
  );
  await wait(650);
};
const pulse = () =>
  page.evaluate(() => {
    const c = document.getElementById("democursor");
    c.style.width = "12px";
    c.style.height = "12px";
    setTimeout(() => { c.style.width = "22px"; c.style.height = "22px"; }, 150);
  });
const zoomTo = async (sel, scale = 1.6) => {
  const box = await page.locator(sel).first().boundingBox();
  if (!box) return;
  await page.evaluate(
    ([ox, oy, s]) => {
      const m = document.querySelector("main");
      m.style.transformOrigin = `${ox}% ${oy}%`;
      m.style.transform = `scale(${s})`;
      const c = document.getElementById("democursor");
      if (c) c.style.opacity = "0";
    },
    [((box.x + box.width / 2) / SIZE.width) * 100, ((box.y + box.height / 2) / SIZE.height) * 100, scale],
  );
  await wait(1200);
};
const zoomReset = async () => {
  await page.evaluate(() => {
    document.querySelector("main").style.transform = "scale(1)";
    const c = document.getElementById("democursor");
    if (c) c.style.opacity = "1";
  });
  await wait(1200);
};
const send = async (text, delay = 18) => {
  await moveTo("form input");
  await page.locator("form input").click();
  await page.locator("form input").pressSequentially(text, { delay });
  await wait(250);
  await moveTo('form button:has-text("Envoyer")');
  await pulse();
  const resp = page.waitForResponse((r) => r.url().includes("/message"), { timeout: 60000 });
  await page.locator('form button:has-text("Envoyer")').click();
  await resp;
  await wait(900);
};
const acceptOne = async () => {
  const btn = page.locator('.card .actions button:has-text("Accepter")').first();
  if ((await btn.count()) === 0) return false;
  await moveTo('.card .actions button:has-text("Accepter")');
  await pulse();
  const resp = page.waitForResponse((r) => r.url().includes("/proposal"), { timeout: 30000 });
  await btn.click();
  await resp;
  await wait(500);
  return true;
};
const challenged = async () =>
  (await page.locator('#edb .section:has(h3:has-text("Challenge")) .entry:not(.muted)').count()) > 0;

// ---- the demo ----
await page.goto(BASE);
await page.locator(".bot").first().waitFor({ timeout: 15000 });
await chrome();
await wait(1200);

await send("Proposer un programme de cash-back lors des paiements chez les commerçants partenaires.", 30);
await wait(600);
await zoomTo("#mappane", 1.5); // the Context Map builds itself from one sentence
await zoomReset();
await wait(900); // read the woven question

await send(ANSWERS[0]); // a free answer → several EDB sections at once
await acceptOne();
await acceptOne();
await zoomTo("#edb", 1.35); // the dossier fills with the user's own words
await zoomReset();

let i = 1;
while (!(await challenged()) && i < ANSWERS.length) {
  await send(ANSWERS[i]);
  i++;
}

if (await challenged()) {
  await wait(900);
  const claim = page.locator('.card', { has: page.locator('.kind:has-text("Affirmation")') }).first();
  if ((await claim.count()) > 0) {
    await claim.evaluate((el) => el.scrollIntoView({ block: "center" })); // centre the card
    await wait(900);
    await zoomTo('.card:has(.kind:has-text("Affirmation"))', 1.9); // a claim + its graph source
    await wait(2800); // hold so the viewer reads the claim AND its verbatim source
    await zoomReset();
  }
  await acceptOne(); // accept a grounded claim
  await acceptOne();
  await wait(700);
}
await wait(1400); // end on the grounded three-pane dossier

await ctx.close(); // flush the video
await browser.close();
console.log("recorded");
