// Records the NadiNet demo video from the running app (http://localhost:3000).
import { chromium } from "playwright";
import fs from "node:fs";

const V = process.argv[2];               // video workspace (cards, output)
const BASE = "http://localhost:3000";
const log = [];                          // caption timeline for the narration script
let t0 = 0;

const INIT = `
(() => {
  if (window.__nadiInit) return; window.__nadiInit = true;
  const css = \`
    #__cap{position:fixed;left:50%;bottom:30px;transform:translateX(-50%);max-width:1120px;width:max-content;
      padding:14px 28px;border-radius:14px;background:rgba(10,13,18,.88);color:#fff;
      font:500 24px/1.4 Inter,system-ui,sans-serif;text-align:center;z-index:2147483646;opacity:0;
      transition:opacity .45s ease;box-shadow:0 10px 30px rgba(0,0,0,.35);pointer-events:none}
    #__cap.on{opacity:1} #__cap.top{top:76px;bottom:auto}
    #__cur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;
      transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
    #__ring{position:fixed;left:0;top:0;width:40px;height:40px;margin:-20px 0 0 -20px;border-radius:50%;
      border:3px solid #fab219;opacity:0;z-index:2147483646;pointer-events:none}
    #__ring.go{animation:__r .5s ease-out}
    @keyframes __r{0%{opacity:.9;transform:scale(.4)}100%{opacity:0;transform:scale(1.4)}}\`;
  const mount = () => {
    if (document.getElementById('__cap') || !document.body) return;
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    const c = document.createElement('div'); c.id = '__cap'; document.body.appendChild(c);
    const r = document.createElement('div'); r.id = '__ring'; document.body.appendChild(r);
    const k = document.createElement('div'); k.id = '__cur';
    k.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7 19 2.6-7.6L20 11z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(k);
    const p = window.__lastPos || [-100, -100];
    k.style.transform = 'translate(' + p[0] + 'px,' + p[1] + 'px)';
    document.addEventListener('mousemove', e => { window.__lastPos = [e.clientX, e.clientY];
      k.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)'; }, true);
    document.addEventListener('mousedown', e => { r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      r.classList.remove('go'); void r.offsetWidth; r.classList.add('go'); }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
  window.__caption = (text, pos) => {
    mount(); const c = document.getElementById('__cap'); if (!c) return;
    c.classList.remove('on');
    setTimeout(() => { c.textContent = text || ''; c.classList.toggle('top', pos === 'top'); if (text) c.classList.add('on'); }, 460);
  };
})();`;

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 810 },
  deviceScaleFactor: 1,
  recordVideo: { dir: V + "/raw", size: { width: 1440, height: 810 } },
});
await ctx.addInitScript(INIT);
const page = await ctx.newPage();
t0 = Date.now();
const wait = (ms) => page.waitForTimeout(ms);
const now = () => ((Date.now() - t0) / 1000).toFixed(1);

async function cap(text, pos) {
  log.push({ t: Number(now()), text });
  await page.evaluate(([t, p]) => window.__caption && window.__caption(t, p), [text, pos]);
}
async function moveTo(loc, steps = 28) {
  const b = await loc.boundingBox();
  if (!b) return null;
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y, { steps });
  return { x, y };
}
async function click(loc, pause = 250) {
  await loc.scrollIntoViewIfNeeded();
  const p = await moveTo(loc);
  await wait(pause);
  if (p) await page.mouse.click(p.x, p.y); else await loc.click();
}
async function smoothScroll(dy, ms = 1800) {
  // scroll the document itself (a mouse wheel over the map would zoom the map instead)
  const steps = 40;
  for (let i = 0; i < steps; i++) {
    await page.evaluate((d) => window.scrollBy(0, d), dy / steps);
    await wait(ms / steps);
  }
}
async function card(name, ms) {
  await page.goto(`file://${V}/${name}.html`);
  await wait(ms);
  await page.evaluate(() => document.body.classList.add("out"));
  await wait(1100);
}

// ---------------------------------------------------------------- intro
await card("intro", 6500);
await card("problem", 10500);

// ---------------------------------------------------------------- landing: cloud vs radar
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.mouse.move(720, 420);
await wait(800);
const slider = page.locator('input[aria-label="Drag to compare optical and radar"]');
const sb = await slider.boundingBox();
const sy = sb.y + sb.height / 2;
await page.mouse.move(sb.x + sb.width * 0.5, sy, { steps: 20 });
await page.mouse.down();
await page.mouse.move(sb.x + sb.width * 0.995, sy, { steps: 25 });
await page.mouse.up();
await cap("July 2025, peak monsoon. The optical satellite sees the Jamuna through 99% cloud.");
await wait(4800);
await page.mouse.down();
await page.mouse.move(sb.x + sb.width * 0.03, sy, { steps: 90 });
await page.mouse.up();
await cap("The radar pass of the same week sees straight through: water is dark, land is bright, and both banks are clear.");
await wait(5200);
await cap("NadiNet reads this free Sentinel-1 radar after every pass, and checks its forecasts against what really happened.");
await wait(4500);
await click(page.getByRole("link", { name: /Watch the replay/ }));
await page.waitForURL("**/demo");
await page.waitForLoadState("networkidle");

// ---------------------------------------------------------------- replay: monsoon playback
await cap("");
await wait(1200);
await page.selectOption("#date", "2023-07-12");
await wait(900);
await click(page.getByRole("button", { name: /Watch the monsoon/ }));
await wait(800);
await cap("A new radar pass every 12 days. NadiNet traces both banks on 871 segments, 200 metres apart.");
await click(page.getByRole("button", { name: "Play passes" }));
await wait(6500);
await cap("Dashed line: the bank at the start of the monsoon. Blue: the bank on the pass you're looking at.");
await wait(6000);

// ---------------------------------------------------------------- freeze
await click(page.getByRole("button", { name: /Freeze the model on/ }));
await wait(600);
await cap("Now we freeze the model on 12 July 2023. It only knows the radar up to that day.");
await wait(5000);
const items = page.locator("aside ol li button");
await cap("It ranks the 20 bank segments most likely to lose land in the next 28 days, each with a plain-language reason.");
for (let i = 0; i < 4; i++) { await moveTo(items.nth(i), 14); await wait(900); }
await wait(1800);
await click(page.getByRole("tab", { name: "Persistence top 20" }));
await cap("For comparison, the obvious baseline: the 20 segments that eroded most in the last 12 weeks.");
await wait(5000);
await click(page.getByRole("tab", { name: "Model top 20" }));
await wait(700);

// ---------------------------------------------------------------- reveal
await click(page.getByRole("button", { name: /Reveal what happened/ }));
await cap("Then we reveal the next check, on 5 August. Green: flagged and really lost land. Red: lost land but missed.");
await wait(6500);
await cap("On this date the model's top 20 caught 9 real losses. The baseline caught none.");
await wait(5000);
await click(items.nth(1));
await cap("Any segment can be opened: its full radar history since 2015, and exactly what happened next.");
await wait(6000);
await click(page.getByRole("button", { name: "Close segment" }));
await wait(500);
await page.mouse.move(1180, 160, { steps: 15 });
await smoothScroll(1400, 2400);
await cap("Across all 65 held-out dates in 2023 to 2025, 42% of the model's top 20 really lost land. The baseline: 4%.");
await wait(7000);

// ---------------------------------------------------------------- dashboard and alerts
await cap("");
await page.goto(BASE + "/dashboard", { waitUntil: "networkidle" });
await wait(1200);
await cap("For local officials, the dashboard shows the latest pass, the ranked list and a weekly PDF brief.");
await wait(5200);
await click(page.getByRole("tab", { name: "Alerts" }));
await wait(1200);
await click(page.getByRole("button", { name: /Go to the latest pass with Warning-eligible/ }));
await wait(1800);
await page.getByRole("tab", { name: "Alerts" }).click();
await wait(600);
await click(page.locator("aside label input[type=checkbox]").first());
await wait(400);
await click(page.getByPlaceholder("Village or union name for the message"));
await page.keyboard.type("Khasrajbari", { delay: 85 });
await wait(400);
await click(page.getByRole("button", { name: /Draft Warning/ }));
await cap("A warning is drafted in Bangla, as a text message and a prerecorded voice call.");
await wait(5500);
await click(page.getByPlaceholder("Official's name"));
await page.keyboard.type("Duty Officer", { delay: 70 });
await click(page.getByPlaceholder("Role (e.g. UNO, PIO)"));
await page.keyboard.type("UNO", { delay: 90 });
await cap("Nothing reaches families until a named official approves it. In this demo it is logged, not sent.");
await wait(1500);
await click(page.getByRole("button", { name: /Approve & send Warning/ }));
await wait(4800);

// ---------------------------------------------------------------- evidence
await cap("");
await page.goto(BASE + "/about#evidence", { waitUntil: "networkidle" });
await wait(1000);
await cap("Every number is measured and published. Bank lines agree with Sentinel-2 to within 20 metres.");
await wait(5200);
await page.mouse.move(700, 500, { steps: 10 });
await smoothScroll(760, 2600);
await cap("The claims ledger shows what is measured, what isn't built yet, and what we refused to claim.");
await wait(5800);
await cap("");
await wait(600);

// ---------------------------------------------------------------- outro
await card("outro", 9500);

const video = page.video();
await ctx.close();
const path = await video.path();
fs.writeFileSync(V + "/captions.json", JSON.stringify(log, null, 1));
console.log(path, ((Date.now() - t0) / 1000).toFixed(1) + "s");
await browser.close();
