import { spawn } from 'node:child_process';

const python = spawn(process.env.PYTHON_BIN || 'python3', ['-m', 'python_service.server'], {
  stdio: 'inherit',
  env: process.env,
});
const frontend = spawn(process.execPath, ['frontend/server.mjs'], {
  stdio: 'inherit',
  env: process.env,
});

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  python.kill('SIGTERM');
  frontend.kill('SIGTERM');
  setTimeout(() => process.exit(code), 250);
}

python.on('exit', (code) => {
  if (!stopping) stop(code || 1);
});
frontend.on('exit', (code) => {
  if (!stopping) stop(code || 1);
});
process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
