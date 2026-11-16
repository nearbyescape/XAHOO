// Renders panels.html: node render-panels.js
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 2000, height: 2400 }, deviceScaleFactor: 1 })).newPage();
  await p.goto('file://' + path.join(__dirname, 'panels.html'));
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
  for (const id of ['about', 'screen', 'numbers', 'disclaimer', 'rules'])
    await (await p.$('#p-' + id)).screenshot({ path: path.join(__dirname, `panel-${id}.png`) });
  await (await p.$('#offline')).screenshot({ path: path.join(__dirname, 'trend-machine-offline-1920x1080.png') });
  await b.close();
})();
