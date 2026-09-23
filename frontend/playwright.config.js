import { defineConfig } from '@playwright/test';

const baseURL = process.env.KHATTAMA_TEST_BASE_URL || 'http://127.0.0.1:8765';
if (process.env.KHATTAMA_TEST_BASE_URL) {
  // Only an identified fixture started by tests/run.mjs may bypass webServer.
  const address = new URL(baseURL);
  if (address.protocol !== 'http:' || address.hostname !== '127.0.0.1' || !process.env.KHATTAMA_TEST_TOKEN) {
    throw Error('Use npm test to start an isolated browser fixture');
  }
  const response = await fetch(`${baseURL}/__test_ready__`, { signal: AbortSignal.timeout(3000) });
  if (!response.ok || (await response.json()).token !== process.env.KHATTAMA_TEST_TOKEN) {
    throw Error('Browser tests require their own isolated fixture');
  }
}

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { baseURL, trace: 'retain-on-failure' },
  webServer: process.env.KHATTAMA_TEST_BASE_URL ? undefined : {
    command: process.platform === 'win32' ? '..\\.venv\\Scripts\\python.exe ..\\tests\\ui_server.py' : '../.venv/bin/python ../tests/ui_server.py',
    env: { KHATTAMA_UI_PORT: '8765', KHATTAMA_UI_READY_FILE: '', KHATTAMA_UI_TOKEN: '' },
    url: `${baseURL}/__test_ready__`,
    reuseExistingServer: false,
    timeout: 30000,
  },
});
