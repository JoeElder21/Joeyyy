// Render an HTML report to a Letter PDF with the pre-installed Playwright Chromium.
// Usage: node scripts/render_report_pdf.mjs <in.html> <out.pdf>
// Env: PLAYWRIGHT_MODULE (default /opt/node22/lib/node_modules/playwright/index.mjs)
//      CHROMIUM_PATH     (default /opt/pw-browsers/chromium)
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const [inHtml, outPdf] = process.argv.slice(2);
if (!inHtml || !outPdf) {
  console.error('usage: render_report_pdf.mjs <in.html> <out.pdf>');
  process.exit(2);
}
const mod = process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs';
const { chromium } = await import(mod);
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' });
const page = await browser.newPage();
const problems = [];
page.on('pageerror', (e) => problems.push('PAGEERROR ' + e.message));
page.on('requestfailed', (r) => problems.push('FAILED ' + r.url().slice(0, 120)));
await page.goto(pathToFileURL(resolve(inHtml)).href, { waitUntil: 'load' });
await page.emulateMedia({ media: 'print' });
await page.evaluate(() => document.fonts.ready);
const fonts = await page.evaluate(() => [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family + ' ' + f.weight));
await page.pdf({ path: outPdf, format: 'Letter', printBackground: true, preferCSSPageSize: true, margin: { top: '0.4in', right: '0.45in', bottom: '0.4in', left: '0.45in' } });
await browser.close();
console.log(JSON.stringify({ out: outPdf, fonts, problems }));
