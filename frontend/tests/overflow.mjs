import { chromium } from '@playwright/test';
const b = await chromium.launch();
const page = await b.newPage();
for (const width of [320,768,1024,1440]) {
  await page.setViewportSize({width,height:900});
  for (const path of ['/#meetings','/#meeting/1','/#upload','/#tasks','/#settings']) {
    await page.goto('http://127.0.0.1:8765'+path);
    await page.waitForLoadState('networkidle');
    const r = await page.evaluate(() => {
      const sw = document.documentElement.scrollWidth, w = window.innerWidth;
      if (sw <= w) return null;
      return {sw,w,el:[...document.querySelectorAll('*')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,cls:String(e.className||'').slice(0,50)})).slice(0,6)};
    });
    if (r) console.log('W',width,'path',path,JSON.stringify(r));
  }
}
await b.close();
