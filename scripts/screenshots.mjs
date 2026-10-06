// Capture README screenshots of the running dashboard.
//   cd app && npm run build && npm start &      (or: npm run dev)
//   node scripts/screenshots.mjs [baseUrl] [outDir]
// Needs the `playwright` package (npm i -D playwright) and a Chromium build.
import { chromium } from "playwright";
import fs from "node:fs";

const base = process.argv[2] ?? "http://localhost:3000";
const out = process.argv[3] ?? "docs/img";
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const settle = (ms = 1500) => page.waitForTimeout(ms);

async function shot(name, opts = {}) {
  await page.screenshot({ path: `${out}/${name}.png`, ...opts });
  console.log("saved", `${out}/${name}.png`);
}

// Landing: hero with the cloudy-optical vs radar comparison
await page.goto(`${base}/`, { waitUntil: "networkidle" });
await settle();
await shot("landing");
await page.locator('input[aria-label="Drag to compare optical and radar"]').fill("70").catch(() => {});
await settle(500);

// Dashboard: latest pass, top 20
await page.goto(`${base}/dashboard`, { waitUntil: "networkidle" });
await settle(3000);
await shot("dashboard");
// open the first segment in the list
await page.locator("ol li button").first().click().catch(() => {});
await settle(2500);
await shot("dashboard_segment");
// alerts tab
await page.getByRole("tab", { name: "Alerts" }).click().catch(() => {});
await settle(800);
await shot("dashboard_alerts");

// Replay demo: monsoon, frozen, revealed
await page.goto(`${base}/demo`, { waitUntil: "networkidle" });
await settle(3000);
await shot("demo_monsoon");
await page.getByRole("button", { name: /Freeze the model/ }).first().click().catch(() => {});
await settle(2500);
await shot("demo_frozen");
await page.getByRole("button", { name: /Reveal what happened/ }).click().catch(() => {});
await settle(2500);
await shot("demo_revealed");
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await settle(1000);
await shot("demo_precision");

// Method & evidence
await page.goto(`${base}/about#evidence`, { waitUntil: "networkidle" });
await settle(1500);
await shot("evidence", { fullPage: false });

// Mobile check
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${base}/`, { waitUntil: "networkidle" });
await settle(1000);
await shot("mobile_landing");

await browser.close();
