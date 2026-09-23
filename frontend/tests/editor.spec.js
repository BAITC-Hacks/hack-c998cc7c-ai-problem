import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('khattama-locale', 'ru'));
});

test('changes to summary immediately uncheck the visible review confirmation', async ({ page }) => {
  await page.goto('/#meeting/1');
  await expect(page.locator('#reviewed')).toBeChecked();
  await page.locator('#summary-text').fill('Обновлённое резюме');
  await expect(page.locator('#reviewed')).not.toBeChecked();
});

test('changes to an assignment immediately uncheck its visible confirmation', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.locator('[data-tab="tasks"]').click();
  await expect(page.locator('[data-confirm="0"]')).toBeChecked();
  await page.locator('[data-task="0:action"]').fill('Уточнить смету');
  await expect(page.locator('[data-confirm="0"]')).not.toBeChecked();
});

test('editing and navigation are locked during a slow save and restored afterwards', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.locator('#summary-text').fill('Сохранённое резюме');
  let release;
  const barrier = new Promise(resolve => { release = resolve; });
  await page.route('**/api/meetings/1/draft', async route => {
    await barrier;
    await route.continue();
  });
  await page.locator('#save').click();
  try {
    await expect(page.locator('#summary-text')).toBeDisabled();
    await expect(page.locator('#locale')).toBeDisabled();
  } finally { release(); }
  await expect(page.locator('#summary-text')).toBeEnabled();
  await expect(page.locator('#summary-text')).toHaveValue('Сохранённое резюме');
});

test('failed save keeps the users draft and allows retry', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.locator('#summary-text').fill('Не потерять этот текст');
  await page.route('**/api/meetings/1/draft', route => route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Revision conflict' }) }));
  await page.locator('#save').click();
  await expect(page.locator('#message')).toContainText('Revision conflict');
  await expect(page.locator('#summary-text')).toHaveValue('Не потерять этот текст');
  await expect(page.locator('#save')).toBeEnabled();
});

test('layout remains within viewport at supported widths', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, title] of [
      ['/#meetings', 'Совещания'],
      ['/#meeting/1', 'Планирование запуска'],
      ['/#upload', 'Новое совещание'],
      ['/#tasks', 'Поручения'],
      ['/#settings', 'Настройки'],
    ]) {
      await page.goto(path);
      await expect(page.locator('h1')).toHaveText(title);
      await expect(page.locator('#app .loader')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${path} at ${width}px`).toBeTruthy();
    }
  }
  expect(errors).toEqual([]);
});

test('search filters the meeting library and can be cleared', async ({ page }) => {
  await page.goto('/#meetings');
  await page.locator('#meeting-search').fill('missing-record-xyz');
  await expect(page.locator('#meeting-list tbody tr')).toHaveCount(0);
  await page.locator('#meeting-search').fill('');
  await expect(page.locator('#meeting-list tbody tr')).toHaveCount(1);
});

test('locale switch preserves unsaved input and discard restores saved draft', async ({ page }) => {
  await page.goto('/#meeting/1');
  const original = await page.locator('#summary-text').inputValue();
  await page.locator('#summary-text').fill('Unsaved locale test');
  await page.locator('#locale').click();
  await expect(page.locator('#summary-text')).toHaveValue('Unsaved locale test');
  await page.locator('#discard').click();
  await page.locator('[data-discard]').click();
  await expect(page.locator('#summary-text')).toHaveValue(original);
  await expect(page.locator('#save')).toBeDisabled();
});

test('reviewed draft can be approved and exported as DOCX and PDF', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.locator('#reviewed').check();
  await page.locator('#approve').click();
  await expect(page.locator('#version option')).toHaveCount(2);
  for (const format of ['docx', 'pdf']) {
    const download = page.waitForEvent('download');
    await page.locator(`[data-export="${format}"]`).click();
    const file = await download;
    expect(file.suggestedFilename()).toBe(`khattama_1.${format}`);
    expect(await file.failure()).toBeNull();
  }
});

test('API defaults explain missing configuration before uploading', async ({ page }) => {
  await page.goto('/#upload');
  await expect(page.locator('[name=mode]')).toHaveValue('HYBRID');
  await expect(page.locator('[name=asr_mode]')).toHaveValue('API');
  await expect(page.locator('#api-setup')).toContainText('ASR_API_KEY');
  await expect(page.locator('button[type=submit]')).toBeDisabled();
  await expect(page.locator('[name=audio_consent]')).not.toBeChecked();
  await expect(page.locator('[name=consent]')).not.toBeChecked();
});

test('API upload persists separately granted audio and text consent', async ({ page }) => {
  await page.route('**/api/health', async route => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), asr_api_configured: true, hybrid_configured: true, asr_api_endpoint: 'speech.example', hybrid_endpoint: 'text.example' } });
  });
  let submitted = '';
  await page.route('**/api/upload', async route => {
    submitted = route.request().postDataBuffer().toString();
    await route.fulfill({ status: 202, json: { meeting_id: 1 } });
  });
  await page.goto('/#upload');
  await page.locator('[name=title]').fill('API upload');
  await page.locator('[name=meeting_at]').fill('2026-09-23T10:00');
  await page.locator('[name=file]').setInputFiles({ name: 'test.wav', mimeType: 'audio/wav', buffer: Buffer.from('test') });
  await page.locator('[name=audio_consent]').check();
  await page.locator('[name=consent]').check();
  await page.locator('button[type=submit]').click();
  await expect(page.locator('#summary-text')).toBeVisible();
  expect(submitted).toContain('"asr_mode":"API"');
  expect(submitted).toContain('"audio_consent":true');
  expect(submitted).toContain('"hybrid_consent":true');
});
