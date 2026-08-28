import puppeteer from 'puppeteer-core';
const browser = await puppeteer.launch({ executablePath: process.argv[2], args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.goto(`file://${process.cwd()}/verbatim.html`, { waitUntil: 'networkidle0' });
await page.evaluateHandle('document.fonts.ready');
await new Promise(r => setTimeout(r, 1200));
await page.pdf({
  path: 'Verbatim.pdf',
  format: 'A4',
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();
console.log('pdf listo');
