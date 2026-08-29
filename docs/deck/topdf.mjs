/**
 * The deck, as a PDF.
 *
 *   node docs/deck/topdf.mjs
 *
 * Reads `verbatim.html`, which references the screenshots in `docs/screenshots/`
 * — so run `docs/capture.mjs` first if the interface has changed.
 */
import puppeteer from "puppeteer-core";

const CHROME =
  process.argv[2] ??
  process.env.CHROME ??
  "/home/alexander-tinoco/.cache/puppeteer/chrome/linux-152.0.7977.42/chrome-linux64/chrome";

const browser = await puppeteer.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.goto(`file://${import.meta.dirname}/verbatim.html`, { waitUntil: "networkidle0" });
await page.evaluateHandle("document.fonts.ready");
await new Promise((r) => setTimeout(r, 1500));

// Every image must have actually loaded; a broken one prints as blank space and
// is very easy to miss in a sixteen-page document.
const broken = await page.$$eval("img", (images) =>
  images.filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.getAttribute("src")),
);
if (broken.length) {
  console.error("images that did not load:", broken);
  process.exit(1);
}

await page.pdf({
  path: new URL("../Verbatim.pdf", import.meta.url).pathname,
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();
console.log(`pdf written · ${await page.$$eval(".page", (p) => p.length).catch(() => "?")} pages`);
