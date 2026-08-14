import { spawn } from 'node:child_process';

const children = [];

function start(name, command, args) {
  const child = spawn(command, args, {
    stdio: 'inherit',
    env: process.env,
  });
  child.serviceName = name;
  children.push(child);
  return child;
}

start('python', process.env.PYTHON_BIN || 'python3', ['-m', 'python_service.server']);
start('frontend', process.execPath, ['frontend/server.mjs']);
if (process.env.SCRAPER_SERVICE_ENABLED !== '0') {
  start('scraper', process.execPath, ['scripts/scraper-service.mjs']);
}

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.killed) child.kill('SIGTERM');
  }
  setTimeout(() => process.exit(code), 250);
}

for (const child of children) {
  child.on('exit', (code, signal) => {
    if (!stopping) {
      console.error(`[${child.serviceName}] exited unexpectedly (code=${code ?? 'null'}, signal=${signal ?? 'none'})`);
      stop(code || 1);
    }
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
