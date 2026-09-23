// Own the server process tree explicitly: Windows venv launchers spawn a child.
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../../', import.meta.url));
const python = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
const server = spawn(python, [path.join(root, 'tests/ui_server.py')], { cwd: root, stdio: 'inherit', windowsHide: true });
server.on('error', error => { console.error(error); process.exitCode = 1; });
let result = 1;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    if (server.exitCode !== null) throw Error('Test server stopped');
    try { ready = (await fetch('http://127.0.0.1:8765/api/health')).ok; } catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!ready) throw Error('Test server did not become ready');
  const runner = spawn(process.execPath, [path.join(root, 'frontend/node_modules/@playwright/test/cli.js'), 'test', ...process.argv.slice(2)], { cwd: path.join(root, 'frontend'), stdio: 'inherit', env: { ...process.env, PLAYWRIGHT_EXTERNAL_SERVER: '1' } });
  result = await new Promise(resolve => runner.on('exit', code => resolve(code ?? 1)));
} finally {
  if (server.pid) {
    if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(server.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    else server.kill('SIGTERM');
  }
}
process.exitCode = result;
