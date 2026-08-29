/**
 * Every screenshot in the README and the deck, taken from the running stack.
 *
 * Nothing here is a mockup: the stack must be up, seeded, and — for the tracing
 * shots — running with OTEL_ENDPOINT set and the tracing profile on.
 *
 *   node docs/capture.mjs
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const CHROME =
  process.env.CHROME ??
  "/home/alexander-tinoco/.cache/puppeteer/chrome/linux-152.0.7977.42/chrome-linux64/chrome";
const OUT = new URL("./screenshots/", import.meta.url).pathname;
const WEB = process.env.WEB ?? "http://localhost:5173";
const API = process.env.API ?? "http://localhost:8000";
const JAEGER = process.env.JAEGER ?? "http://localhost:16686";
const PANEL = `${WEB}/${process.env.VITE_PANEL_PATH ?? "panel"}`;
const DEMO = { email: "demo@acme.com", password: "correct-horse-battery" };
const RESUME_PDF = new URL("../api/tests/golden/pdfs/kowalski.pdf", import.meta.url).pathname;

mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  args: ["--no-sandbox", "--force-device-scale-factor=2"],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 },
});

const shot = async (page, name, options = {}) => {
  await wait(450);
  await page.screenshot({ path: `${OUT}${name}.png`, ...options });
  console.log("  ", name);
};

/**
 * Crop to an element, with a little air around it.
 *
 * `clip` is measured from the top of the document while `getBoundingClientRect`
 * is measured from the top of the viewport, so the scroll offset has to be added
 * back. Without it a shot of anything below the fold silently captures whatever
 * happens to sit at that height near the top of the page — which is exactly what
 * the first attempt at the confirmation dialog produced.
 */
const clipTo = async (page, selector, pad = 20) => {
  const box = await page.$eval(selector, (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height };
  });
  return {
    clip: {
      x: Math.max(0, box.x - pad),
      y: Math.max(0, box.y - pad),
      width: box.width + pad * 2,
      height: box.height + pad * 2,
    },
  };
};

const signIn = async (page) => {
  await page.goto(PANEL, { waitUntil: "networkidle0" });
  await page.type("input[type=email]", DEMO.email);
  await page.type("input[type=password]", DEMO.password);
  await page.click("button[type=submit]");
  await page.waitForSelector(".exhibit", { timeout: 20000 });
  await wait(700);
};

/** Choose an opening by slug, through the API, so ordering never matters. */
const openBySlug = async (page, slug) => {
  // Same origin: connect-src 'self' blocks a cross-origin fetch from the page,
  // and nginx proxies /api through anyway.
  const list = await page.evaluate(
    async () => (await fetch("/api/v1/openings", { credentials: "include" })).json(),
  );
  const wanted = list.find((o) => o.slug === slug);
  const picker = await page.$("select.field");
  if (picker && wanted) {
    await page.select("select.field", wanted.id);
    await wait(900);
  }
  return wanted;
};

const rowNamed = async (page, name) => {
  const index = (
    await page.$$eval(".exhibit .exhibit-name", (n) => n.map((x) => x.textContent))
  ).findIndex((n) => n?.includes(name));
  if (index < 0) throw new Error(`no row for ${name}`);
  await page.evaluate((i) => document.querySelectorAll(".exhibit")[i].click(), index);
  await page.waitForSelector(".plate-name", { timeout: 10000 });
  await wait(700);
};

console.log("the public site");

// ─── 01 the landing page ───
const site = await browser.newPage();
await site.goto(`${WEB}/`, { waitUntil: "networkidle0" });
await wait(900);
await shot(site, "01-landing", { fullPage: true });

// ─── 02 the opening, on a phone ───
const phone = await browser.newPage();
await phone.setViewport({ width: 430, height: 932, deviceScaleFactor: 2 });
await phone.goto(`${WEB}/apply/data-analyst-demo`, { waitUntil: "networkidle0" });
await wait(600);
await shot(phone, "02-opening-mobile", { fullPage: true });

// ─── 03 the form, with the fields and the consent ───
const form = await browser.newPage();
await form.goto(`${WEB}/apply/data-analyst-demo`, { waitUntil: "networkidle0" });
await wait(600);
await form.type('input[name="full_name"]', "Rosa Delgado");
// Unique per run: an applicant may apply to an opening only once, so a fixed
// address makes the second capture run hang on a 409 that never navigates.
const APPLICANT = `rosa.delgado.${Date.now()}@example.com`;
await form.type('input[name="email"]', APPLICANT);
await form.type('input[name="phone"]', "+34 600 112 233");
await shot(form, "03-application-form", await clipTo(form, "form"));

// ─── 04 screening questions, and that neither answer is hinted at ───
const questions = await browser.newPage();
await questions.goto(`${WEB}/apply/night-shift-nurse`, { waitUntil: "networkidle0" });
await wait(600);
await questions.evaluate(() =>
  document.querySelectorAll(".question")[0].querySelectorAll("input[type=radio]")[1].click(),
);
await wait(300);
await shot(questions, "04-screening-questions", await clipTo(questions, ".questions"));

// ─── 05 the confirmation, because an application cannot be unsent ───
await form.bringToFront();
const file = await form.$('input[type="file"]');
await file.uploadFile(RESUME_PDF);
await form.click('input[type="checkbox"]');
await wait(400);
await form.click('button[type="submit"]');
await form.waitForSelector("dialog.confirm[open]", { timeout: 10000 });
await shot(form, "05-send-confirmation", await clipTo(form, "dialog.confirm", 26));

// ─── 06 the receipt, and the promise it makes ───
await form.click("dialog.confirm .control.primary");
await form.waitForFunction(() => location.pathname.includes("/received/"), { timeout: 25000 });
await wait(900);
await shot(form, "06-application-received", await clipTo(form, ".sent", 26));

console.log("the panel");

// ─── 07 sign-in ───
const gate = await browser.newPage();
await gate.goto(PANEL, { waitUntil: "networkidle0" });
await gate.type("input[type=email]", DEMO.email);
await gate.type("input[type=password]", "correct-horse-battery");
await wait(300);
await shot(gate, "07-sign-in", await clipTo(gate, ".gate > *", 24));

// ─── 08 the ranking ───
const panel = await browser.newPage();
await signIn(panel);
await openBySlug(panel, "data-analyst-demo");
await shot(panel, "08-ranking");

// ─── 09 a candidate, with the evidence beside every score ───
await rowNamed(panel, "Elena Vargas");
await shot(panel, "09-candidate-evidence");

// ─── 10 reading one application, with the list out of the way ───
await panel.evaluate(() => document.querySelector('button[aria-label="Hide the list"]').click());
await wait(700);
await shot(panel, "10-focused-reading", { captureBeyondViewport: false });
await panel.evaluate(() => document.querySelector(".reopen")?.click());
await wait(600);

// ─── 10b search: a surname, an address, or anything inside a résumé ───
await panel.type(".search input", "raman");
await wait(1200);
await shot(panel, "21-search", await clipTo(panel, ".register.exhibits", 0));
await panel.evaluate(() => {
  const box = document.querySelector(".search input");
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(box, "");
  box.dispatchEvent(new Event("input", { bubbles: true }));
});
await wait(900);

// ─── 10c a decision, with the person and the reason beside the score ───
await rowNamed(panel, "Elena Vargas");
const decisionBlock = (await panel.$("div.decided")) ? "div.decided" : ".decision-form";
if (decisionBlock === ".decision-form") {
  await panel.type('input[placeholder*="Your name"]', "Ana Ruiz");
  await panel.type('input[placeholder*="Why"]', "Strongest evidence on SQL and measured impact.");
}
// Scroll it into the viewport and take the viewport: the plate scrolls inside
// its own container, so a crop computed from anything in it points at document
// coordinates that were never painted.
await panel.evaluate((selector) => {
  document.querySelector(selector)?.scrollIntoView({ block: "center", behavior: "instant" });
}, decisionBlock);
await wait(700);
await shot(panel, "22-decision", { captureBeyondViewport: false });

// ─── 11 the concealed layer, on the tampered résumé ───
await rowNamed(panel, "Tomás Ibarra (tampered)");
if (await panel.$(".concealed")) {
  await shot(panel, "11-concealed-layer", await clipTo(panel, "section:has(.concealed)", 22));
}

// ─── 12 seen before: one document, two identities ───
if (await panel.$(".seen-before")) {
  await shot(panel, "12-seen-before", await clipTo(panel, "section:has(.seen-before)", 22));
}

// ─── 13 the résumé itself, rendered as an image ───
const documentTab = await panel.$$("button.control");
for (const button of documentTab) {
  const label = (await button.evaluate((e) => e.textContent)) ?? "";
  if (label.trim().toLowerCase() === "document") {
    await button.click();
    break;
  }
}
await wait(1600);
await shot(panel, "13-resume-document");

// ─── 14 comparing two candidates ───
await panel.evaluate(() =>
  document.querySelector('button[aria-label="Compare candidates"]').click(),
);
await wait(400);
const pickable = await panel.$$eval(".exhibit:not([disabled])", (n) => n.length);
if (pickable >= 2) {
  await panel.evaluate(() => {
    const rows = document.querySelectorAll(".exhibit:not([disabled])");
    rows[0].click();
    rows[1].click();
  });
  await panel.waitForSelector(".compare-verdict", { timeout: 15000 });
  await wait(800);
  await shot(panel, "14-compare");
}

// ─── 15 screening answers, on the other opening ───
await panel.evaluate(() =>
  document.querySelector('button[aria-label="Compare candidates"]').click(),
);
await wait(300);
await openBySlug(panel, "night-shift-nurse");
await shot(panel, "15-said-no-list", await clipTo(panel, ".register.exhibits", 0));
await rowNamed(panel, "Bo Nilsson");
if (await panel.$("ul.stated")) {
  await shot(panel, "16-stated-by-applicant", await clipTo(panel, "section:has(ul.stated)", 22));
}

console.log("the shared link");

// ─── 17 a shared shortlist, seen by someone with no session ───
await openBySlug(panel, "data-analyst-demo");
await panel.evaluate(() => document.querySelector('button[aria-label="Share the shortlist"]').click());
await panel.waitForSelector(".share-made", { timeout: 15000 });
await wait(500);
await shot(panel, "17-share-made", await clipTo(panel, ".share-made", 26));

const url = await panel.$eval(".share-made input, .share-made code, .share-made a", (el) =>
  el.value ?? el.textContent,
);
const stranger = await browser.createBrowserContext();
const shared = await stranger.newPage();
await shared.setViewport({ width: 1440, height: 1100, deviceScaleFactor: 2 });
await shared.goto(url.trim(), { waitUntil: "networkidle0" });
await wait(900);
await shot(shared, "18-shared-shortlist", { fullPage: true });
await stranger.close();

console.log("the instruments");

// ─── 19 a trace, with every query under the request ───
const traces = await browser.newPage();
await traces.goto(`${JAEGER}/`, { waitUntil: "domcontentloaded" });
const list = await traces.evaluate(
  async () => (await fetch("/api/traces?service=verbatim-api&limit=60")).json(),
);
// The panel's ranked list specifically, not merely the biggest trace: the
// caption in the README and the deck makes a claim about *that* request — a
// constant thirteen queries however many candidates there are — and an
// application upload would have illustrated a different sentence entirely.
const ranked = list.data
  .filter((t) =>
    t.spans.some((s) => s.operationName.includes("/applications") && !s.references?.length),
  )
  .sort((a, b) => b.spans.length - a.spans.length);
if (!ranked.length) throw new Error("no trace of the ranked list — generate some panel traffic");
await traces.goto(`${JAEGER}/trace/${ranked[0].traceID}`, { waitUntil: "networkidle0" });
await wait(3000);
await shot(traces, "19-trace-waterfall");

// ─── 20 the search, so the shape of the traffic is visible ───
await traces.goto(`${JAEGER}/search?service=verbatim-api&limit=40`, { waitUntil: "networkidle0" });
await wait(3000);
await shot(traces, "20-trace-search");

// The capture creates one application; leave the demo as it was found. Erasure
// is a real endpoint with a real audit trail, so this exercises it too.
const erased = await panel.evaluate(async (email) => {
  const response = await fetch("/api/v1/data-subject/erase", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email }),
  });
  return response.status;
}, APPLICANT);
console.log("  cleaned up the captured applicant:", erased);

await browser.close();
console.log("done");
