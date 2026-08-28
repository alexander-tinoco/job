import puppeteer from 'puppeteer-core';
const BASE = 'http://localhost:5173';
const OUT = new URL('./shots/', import.meta.url).pathname;
const browser = await puppeteer.launch({
  executablePath: process.argv[2], args: ['--no-sandbox'],
  defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
const shot = async (n, o = {}) => { await new Promise(r => setTimeout(r, 500)); await page.screenshot({ path: `${OUT}${n}.png`, ...o }); console.log('  ', n); };

const clickRowContaining = async (needle) => {
  const ok = await page.evaluate((text) => {
    const row = [...document.querySelectorAll('.exhibit')].find(e => e.innerText.includes(text));
    if (!row) return false;
    row.click();
    return true;
  }, needle);
  if (!ok) throw new Error(`no row containing "${needle}"`);
  await page.waitForSelector('.plate-name');
  await new Promise(r => setTimeout(r, 600));
};

await page.goto(`${BASE}/panel`, { waitUntil: 'networkidle0' });
await page.type('input[type=email]', 'demo@acme.com');
await page.type('input[type=password]', 'correct-horse-battery');
await page.click('button[type=submit]');
await page.waitForSelector('.exhibit', { timeout: 20000 });

await clickRowContaining('tampered');
await page.waitForSelector('.concealed', { timeout: 10000 });
await shot('10-concealed-layer');

await page.evaluate(() => {
  const b = [...document.querySelectorAll('.registers .control')].find(x => x.innerText.includes('Document'));
  b.scrollIntoView({ block: 'center' }); b.click();
});
await new Promise(r => setTimeout(r, 2500));
await shot('11-document-pages');

await clickRowContaining('shortlisted');
await page.evaluate(() => document.querySelector('.decided')?.scrollIntoView({ block: 'center' }));
await shot('12-decision');

await page.evaluate(() => document.querySelectorAll('.register')[1].scrollTo(0, 0));
await page.click('button[aria-label="Hide the list"]');
await shot('13-focused');

await browser.close();
console.log('listo');
