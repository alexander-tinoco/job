import puppeteer from 'puppeteer-core';
const BASE = 'http://localhost:5173';
const OUT = '/home/alexander-tinoco/Documentos/github/job/docs/deck/shots/';

const browser = await puppeteer.launch({
  executablePath: process.argv[2], args: ['--no-sandbox'],
  defaultViewport: { width: 430, height: 1500, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
await page.goto(`${BASE}/apply/data-analyst-demo`, { waitUntil: 'networkidle0' });

await page.type('input[name=full_name]', 'Rosa Delgado');
await page.type('input[name=email]', 'rosa.delgado@example.com');
await page.type('input[name=phone]', '+34 600 112 233');
await page.type('input[name=linkedin_url]', 'linkedin.com/in/rosadelgado');

const chooser = page.waitForFileChooser();
await page.click('.dropzone button');
(await chooser).accept(['/home/alexander-tinoco/Documentos/github/job/api/tests/golden/pdfs/kowalski.pdf']);
await new Promise(r => setTimeout(r, 600));
await page.click('.consent input');
await new Promise(r => setTimeout(r, 400));

// Clip to the form itself — from the "Apply" heading down to the submit button —
// so all four fields, the file, the consent box and the button are in frame.
const box = await page.evaluate(() => {
  const heading = [...document.querySelectorAll('h2')].find(h => h.innerText.trim() === 'Apply');
  const submit = document.querySelector('button[type=submit]');
  const a = heading.getBoundingClientRect();
  const b = submit.getBoundingClientRect();
  return {
    x: Math.max(0, a.left - 22),
    y: Math.max(0, a.top - 14),
    width: Math.min(window.innerWidth, a.width + 44),
    height: b.bottom - a.top + 30,
  };
});
await page.screenshot({ path: `${OUT}02-form-filled.png`, clip: box });
console.log(`  02-form-filled  ${Math.round(box.width)}x${Math.round(box.height)} css px`);
await browser.close();
