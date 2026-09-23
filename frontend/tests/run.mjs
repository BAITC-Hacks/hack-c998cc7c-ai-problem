// Own the server process tree explicitly: Windows venv launchers spawn a child.
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const root = fileURLToPath(new URL('../../', import.meta.url));
const python = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const temporaryRoot = path.resolve(os.tmpdir());
const directory = await mkdtemp(path.join(temporaryRoot, 'khattama-browser-'));
const readyFile = path.join(directory, 'ready.json');
const token = randomUUID();
const server = spawn(python, [path.join(root, 'tests/ui_server.py')], {
  cwd: root, stdio: 'inherit', windowsHide: true,
  env: { ...process.env, KHATTAMA_UI_PORT: '0', KHATTAMA_UI_READY_FILE: readyFile, KHATTAMA_UI_TOKEN: token },
});
let serverError;
server.on('error', error => { serverError = error; });
let runner;
let result = 1;
let interrupted = false;

async function stop(child) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise(resolve => child.once('exit', resolve));
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
  } else {
    child.kill('SIGTERM');
  }
  const force = setTimeout(() => child.kill('SIGKILL'), 5000);
  try { await exited; } finally { clearTimeout(force); }
}

// The default signal action would skip finally and leave the fixture running.
const interrupt = () => { interrupted = true; void stop(runner); };
process.on('SIGINT', interrupt);
process.on('SIGTERM', interrupt);
try {
  let baseURL;
  for (let attempt = 0; attempt < 60; attempt++) {
    if (interrupted) throw Error('Test run interrupted');
    if (serverError) throw serverError;
    if (server.exitCode !== null || server.signalCode !== null) throw Error('Test server stopped');
    try {
      const ready = JSON.parse(await readFile(readyFile, 'utf8'));
      if (ready.token !== token || !Number.isInteger(ready.port)) throw Error('Unexpected fixture identity');
      const candidate = `http://127.0.0.1:${ready.port}`;
      const response = await fetch(`${candidate}/__test_ready__`, { signal: AbortSignal.timeout(1000) });
      if (response.ok && (await response.json()).token === token) baseURL = candidate;
    } catch {}
    if (baseURL) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!baseURL) throw Error('Test server did not become ready');
  runner = spawn(process.execPath, [path.join(root, 'frontend/node_modules/@playwright/test/cli.js'), 'test', ...process.argv.slice(2)], {
    cwd: path.join(root, 'frontend'), stdio: 'inherit', windowsHide: true,
    env: { ...process.env, KHATTAMA_TEST_BASE_URL: baseURL, KHATTAMA_TEST_TOKEN: token },
  });
  result = await new Promise((resolve, reject) => {
    runner.once('error', reject);
    runner.once('exit', code => resolve(code ?? 1));
  });
} catch (error) {
  console.error(error.message);
} finally {
  await stop(runner);
  await stop(server);
  // Windows process-tree termination cannot execute Python cleanup handlers.
  const cleanupPath = path.resolve(directory);
  if (path.dirname(cleanupPath) !== temporaryRoot || !path.basename(cleanupPath).startsWith('khattama-browser-')) {
    throw Error('Refusing to clean up outside the generated test directory');
  }
  await rm(cleanupPath, { recursive: true, force: true, maxRetries: 3 });
  process.removeListener('SIGINT', interrupt);
  process.removeListener('SIGTERM', interrupt);
}
process.exitCode = interrupted ? 130 : result;
