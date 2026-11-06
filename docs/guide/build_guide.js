// Génère docs/Guide_EURUSD_M5_Analyzer.pdf à partir de guide.html
// Usage : node docs/guide/build_guide.js   (nécessite : npm i playwright)
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const src = path.resolve(__dirname, "guide.html");
  const out = path.resolve(__dirname, "..", "Guide_EURUSD_M5_Analyzer.pdf");
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto("file://" + src, { waitUntil: "networkidle" });
  await page.pdf({
    path: out,
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: `<div style="width:100%;font:7.5pt Inter,sans-serif;color:#8a93a3;padding:0 17mm;display:flex;justify-content:space-between">
      <span>EURUSD M5 Analyzer — Guide d'utilisation</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  });
  await browser.close();
  console.log("PDF créé :", out);
})();
