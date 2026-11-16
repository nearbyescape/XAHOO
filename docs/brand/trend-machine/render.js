// Renders brand.html to PNGs at Twitch sizes: node render.js
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1400, height: 1400 }, deviceScaleFactor: 1 })).newPage();
  await p.goto('file://' + path.join(__dirname, 'brand.html'));
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  await (await p.$('#profile')).screenshot({ path: path.join(__dirname, 'trend-machine-profile-800.png') });
  await (await p.$('#banner')).screenshot({ path: path.join(__dirname, 'trend-machine-banner-1200x480.png') });
  // preview at the size Twitch shows the avatar (circle crop)
  const b64 = require('fs').readFileSync(path.join(__dirname, 'trend-machine-profile-800.png')).toString('base64');
  await p.setContent(`<body style="margin:0;background:#18181b;display:flex;gap:24px;align-items:center;padding:24px">
    ${[300, 70, 50, 28].map(s => `<img src="data:image/png;base64,${b64}" style="width:${s}px;height:${s}px;border-radius:50%">`).join('')}</body>`);
  await p.waitForTimeout(300);
  await p.screenshot({ path: path.join(__dirname, 'preview-avatar-sizes.png'), clip: { x: 0, y: 0, width: 560, height: 350 } });
  await b.close();
})();
