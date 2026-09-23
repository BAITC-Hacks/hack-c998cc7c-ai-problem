import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('khattama-locale', 'ru'));
});

async function prepareUpload(page) {
  await page.route('**/api/health', async route => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), ffmpeg_available: true, asr_api_configured: true, hybrid_configured: true } });
  });
  await page.goto('/#upload');
  await page.locator('[name=title]').fill('Проверка загрузки');
  await page.locator('[name=meeting_at]').fill('2026-09-23T10:00');
  await page.locator('[name=participants]').fill('Айдана, Тимур');
  await page.locator('[name=file]').setInputFiles({ name: 'test.wav', mimeType: 'audio/wav', buffer: Buffer.from('test') });
  await page.locator('[name=audio_consent]').check();
  await page.locator('[name=consent]').check();
}

test('changing language preserves the selected recording, metadata and consent', async ({ page }) => {
  await prepareUpload(page);
  await page.locator('#locale').click();
  await expect(page.locator('[name=title]')).toHaveValue('Проверка загрузки');
  await expect(page.locator('[name=meeting_at]')).toHaveValue('2026-09-23T10:00');
  await expect(page.locator('[name=participants]')).toHaveValue('Айдана, Тимур');
  await expect(page.locator('[name=audio_consent]')).toBeChecked();
  await expect(page.locator('[name=consent]')).toBeChecked();
  expect(await page.locator('[name=file]').evaluate(input => input.files[0]?.name)).toBe('test.wav');
});

test('slow upload locks edits, rejects duplicate submission and restores its route', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await prepareUpload(page);
  let submissions = 0;
  let release;
  const barrier = new Promise(resolve => { release = resolve; });
  await page.route('**/api/upload', async route => {
    submissions++;
    await barrier;
    await route.fulfill({ status: 202, json: { meeting_id: 1 } });
  });
  await page.locator('button[type=submit]').click();
  try {
    await expect(page.locator('[name=title]')).toBeDisabled();
    await expect(page.locator('[name=mode]')).toBeDisabled();
    await expect(page.locator('#locale')).toBeDisabled();
    await expect(page.locator('#upload-progress')).toBeVisible();
    await page.evaluate(() => {
      document.querySelector('[name=mode]').dispatchEvent(new Event('change'));
      document.querySelector('#upload-form').dispatchEvent(new Event('submit', { cancelable: true }));
      location.hash = 'tasks';
    });
    await expect(page).toHaveURL(/#upload$/);
    await expect(page.locator('button[type=submit]')).toBeDisabled();
  } finally { release(); }
  await expect(page.locator('#summary-text')).toBeVisible();
  await expect(page.locator('#locale')).toBeEnabled();
  expect(submissions).toBe(1);
  expect(errors).toEqual([]);
});

test('failed upload unlocks the form and retains the selected file for retry', async ({ page }) => {
  await prepareUpload(page);
  await page.route('**/api/upload', route => route.fulfill({ status: 503, json: { detail: 'Upload temporarily unavailable' } }));
  await page.locator('button[type=submit]').click();
  await expect(page.locator('#message')).toContainText('Upload temporarily unavailable');
  await expect(page.locator('[name=title]')).toHaveValue('Проверка загрузки');
  await expect(page.locator('[name=title]')).toBeEnabled();
  await expect(page.locator('button[type=submit]')).toBeEnabled();
  await expect(page.locator('#locale')).toBeEnabled();
  await expect(page.locator('#upload-progress')).toBeHidden();
  expect(await page.locator('[name=file]').evaluate(input => input.files[0]?.name)).toBe('test.wav');
});

test('obsolete evidence can be removed and the assignment requires review again', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.locator('[data-tab=tasks]').click();
  const evidenceCount = await page.locator('[data-remove-evidence^="task:0:"]').count();
  expect(evidenceCount).toBeGreaterThan(0);
  await page.locator('[data-remove-evidence="task:0:0"]').click();
  await expect(page.locator('[data-remove-evidence^="task:0:"]')).toHaveCount(evidenceCount - 1);
  await expect(page.locator('[data-confirm="0"]')).not.toBeChecked();
  await expect(page.locator('#save')).toBeEnabled();
  let saved;
  await page.route('**/api/meetings/1/draft', async route => {
    saved = route.request().postDataJSON().draft;
    await route.fulfill({ status: 409, json: { detail: 'Keep fixture unchanged' } });
  });
  await page.locator('#save').click();
  await expect(page.locator('#message')).toContainText('Keep fixture unchanged');
  expect(saved.assignments[0].evidence).toHaveLength(evidenceCount - 1);
  expect(saved.assignments[0].review).toBe('needs_review');
});

test('blank required fields give an actionable message without losing the draft', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.locator('[data-tab=tasks]').click();
  await page.locator('[data-task="0:action"]').fill('');
  await page.locator('#save').click();
  await expect(page.locator('#message')).toContainText('Поручение 1: заполните действие');
  await expect(page.locator('[data-task="0:action"]')).toHaveValue('');
  await expect(page.locator('[data-task="0:action"]')).toBeEnabled();
});

test('keyboard tabs expose the currently labelled protocol panel', async ({ page }) => {
  await page.goto('/#meeting/1');
  await page.getByRole('tab', { name: 'Резюме' }).focus();
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Поручения' })).toBeFocused();
  await expect(page.getByRole('tabpanel', { name: 'Поручения' })).toBeVisible();
  await page.keyboard.press('Home');
  await expect(page.getByRole('tab', { name: 'Резюме' })).toBeFocused();
  await expect(page.getByRole('tabpanel', { name: 'Резюме' })).toBeVisible();
});

test('a delayed meeting response does not replace a newer route', async ({ page }) => {
  let release;
  const barrier = new Promise(resolve => { release = resolve; });
  await page.route('**/api/meetings/1', async route => {
    await barrier;
    await route.continue();
  });
  const requested = page.waitForRequest('**/api/meetings/1');
  await page.goto('/#meeting/1');
  await requested;
  await page.locator('[data-nav=settings]').click();
  await expect(page.locator('h1')).toHaveText('Настройки');
  const completed = page.waitForResponse('**/api/meetings/1');
  release();
  await completed;
  await page.waitForLoadState('networkidle');
  await expect(page.locator('h1')).toHaveText('Настройки');
  await expect(page.locator('#editor-fields')).toHaveCount(0);
});
