import puppeteer from 'puppeteer-core';

const CHROME = process.argv[2];
const BASE = 'http://localhost:5173';
const OUT = new URL('./shots/', import.meta.url).pathname;

const browser = await puppeteer.launch({
  executablePath: CHROME,
  args: ['--no-sandbox', '--force-device-scale-factor=2'],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 },
});

const shot = async (page, name, opts = {}) => {
  await new Promise(r => setTimeout(r, 450));
  await page.screenshot({ path: `${OUT}${name}.png`, ...opts });
  console.log('  ', name);
};

// ─── The applicant, on a phone ───
const phone = await browser.newPage();
await phone.setViewport({ width: 430, height: 932, deviceScaleFactor: 2 });
await phone.goto(`${BASE}/apply/data-analyst-demo`, { waitUntil: 'networkidle0' });
await shot(phone, '01-opening-mobile', { fullPage: true });

await phone.type('input[name=full_name]', 'Rosa Delgado');
await phone.type('input[name=email]', 'rosa.delgado@example.com');
await phone.type('input[name=phone]', '+34 600 112 233');
const chooser = phone.waitForFileChooser();
await phone.click('.dropzone button');
(await chooser).accept(['/home/alexander-tinoco/Documentos/github/job/api/tests/golden/pdfs/kowalski.pdf']);
await new Promise(r => setTimeout(r, 500));
await phone.click('.consent input');
await shot(phone, '02-form-filled', { fullPage: true });

await phone.click('button[type=submit]');
await phone.waitForSelector('dialog.confirm[open]');
await shot(phone, '03-confirm-send');
await phone.click('dialog.confirm .control.primary');
await phone.waitForSelector('.sent h1', { timeout: 25000 });
await shot(phone, '04-sent', { fullPage: true });
await phone.close();

// ─── The panel ───
const page = await browser.newPage();
await page.goto(BASE, { waitUntil: 'networkidle0' });
await shot(page, '05-signin');

await page.type('input[type=email]', 'demo@acme.com');
await page.type('input[type=password]', 'correct-horse-battery');
await page.click('button[type=submit]');
await page.waitForSelector('.exhibit', { timeout: 20000 });
await shot(page, '06-ranking');

// Search by surname.
await page.type('.search input', 'Vargas');
await new Promise(r => setTimeout(r, 900));
await shot(page, '07-search-surname');
await page.click('.search input', { clickCount: 3 });
await page.keyboard.press('Backspace');
await new Promise(r => setTimeout(r, 700));

// The top candidate: findings and cited evidence.
const rows = await page.$$('.exhibit');
await rows[0].click();
await page.waitForSelector('.plate-name');
await shot(page, '08-findings');

// Raking light: hovering a locator lifts its quote in the transcript.
await page.evaluate(() => document.querySelectorAll('.register')[1].scrollTo(0, 620));
const loc = await page.$('.locator');
if (loc) await loc.hover();
await shot(page, '09-raking-light');

// The tampered résumé — the set piece.
for (const row of await page.$$('.exhibit')) {
  const t = await page.evaluate(e => e.innerText, row);
  if (t.includes('concealed')) { await row.click(); break; }
}
await page.waitForSelector('.concealed', { timeout: 10000 });
await page.evaluate(() => document.querySelectorAll('.register')[1].scrollTo(0, 0));
await shot(page, '10-concealed-layer');

// The document, rendered server-side as images.
await page.evaluate(() => {
  const b = [...document.querySelectorAll('.registers .control')].find(x => x.innerText.includes('Document'));
  b?.scrollIntoView({ block: 'center' }); b?.click();
});
await new Promise(r => setTimeout(r, 2200));
await shot(page, '11-document-pages');

// A recorded decision.
for (const row of await page.$$('.exhibit')) {
  const t = await page.evaluate(e => e.innerText, row);
  if (t.includes('shortlisted')) { await row.click(); break; }
}
await page.waitForSelector('.decided', { timeout: 10000 });
await page.evaluate(() => document.querySelector('.decided')?.scrollIntoView({ block: 'center' }));
await shot(page, '12-decision');

// Focused reading.
await page.evaluate(() => document.querySelectorAll('.register')[1].scrollTo(0, 0));
await page.click('button[aria-label="Hide the list"]');
await shot(page, '13-focused');

await browser.close();
console.log('listo');
