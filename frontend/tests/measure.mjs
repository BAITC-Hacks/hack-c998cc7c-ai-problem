import { chromium } from '@playwright/test';
const b = await chromium.launch();
const page = await b.newPage();
await page.setViewportSize({width:320,height:900});
await page.goto('http://127.0.0.1:8765/#meetings');
await page.waitForLoadState('networkidle');
const r = await page.evaluate(() => {
  const sel = el => ({cls:el.className||el.id||el.tagName, sw:el.scrollWidth, w:el.getBoundingClientRect().width, min:getComputedStyle(el).minWidth, max:getComputedStyle(el).maxWidth, ow:getComputedStyle(el).overflowWrap, ws:getComputedStyle(el).whiteSpace, fs:getComputedStyle(el).flexShrink, fb:getComputedStyle(el).flexBasis});
  const h = document.querySelector('.sidebar');
  const out = [];
  h.querySelectorAll('*').forEach(e => { if (e.scrollWidth > e.clientWidth + 1) out.push({tag:e.tagName,cls:String(e.className||'').slice(0,40),sw:e.scrollWidth,cw:e.clientWidth}); });
  return {header:{cw:h.clientWidth,sw:h.scrollWidth}, items:out.slice(0,20)};
});
console.log(JSON.stringify(r,null,1));
await b.close();
