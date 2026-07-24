/**
 * `npm run dev` — the whole stack in one terminal:
 *   1. requires Docker (Postgres lives there)
 *   2. docker compose up -d --wait
 *   3. creates the Python venvs on first run if they are missing
 *   4. alembic upgrade head
 *   5. mock-openAPI :4001, server :4000
 *   6. seeds the demo data, but only when there is none
 *   7. MiniApp dev server
 *
 * Ctrl+C stops everything. `npm run dev:app` runs the MiniApp alone.
 */
import { execSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(appDir, '..');
const serverDir = path.join(root, 'server');
const mockDir = path.join(root, 'mock-openAPI');

const python = (dir) =>
  path.join(
    dir,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
  );

// Docker first — everything else depends on Postgres.
try {
  execSync('docker info', { stdio: 'ignore' });
} catch {
  console.error(
    '\nDocker is not running. Start Docker Desktop, wait for it to go green, then run `npm run dev` again.\n'
  );
  process.exit(1);
}

// First run on a fresh clone: build the venvs instead of complaining.
const basePython = (() => {
  for (const candidate of process.platform === 'win32'
    ? ['py', 'python']
    : ['python3', 'python']) {
    try {
      execSync(`${candidate} --version`, { stdio: 'ignore' });
      return candidate;
    } catch {
      /* try the next one */
    }
  }
  console.error('\nNo Python found on PATH — install Python 3.12+ first.\n');
  process.exit(1);
})();

for (const dir of [serverDir, mockDir]) {
  if (existsSync(python(dir))) continue;
  console.log(`→ creating venv in ${path.basename(dir)} (first run)`);
  execSync(`${basePython} -m venv .venv`, { cwd: dir, stdio: 'inherit' });
  execSync(`"${python(dir)}" -m pip install -q -r requirements.txt`, {
    cwd: dir,
    stdio: 'inherit',
    shell: true,
  });
}

console.log('→ docker compose up -d --wait');
execSync('docker compose up -d --wait', { cwd: root, stdio: 'inherit' });

// The app no longer creates its own tables; migrations own the schema.
console.log('→ alembic upgrade head');
execSync(`"${python(serverDir)}" -m alembic upgrade head`, {
  cwd: serverDir,
  stdio: 'inherit',
  shell: true,
});

// --reload on both Python servers, quiet logs so the MiniApp CLI's output
// stays readable.
const children = [
  spawn(
    python(mockDir),
    ['-m', 'uvicorn', 'main:app', '--port', '4001', '--log-level', 'warning', '--reload'],
    { cwd: mockDir, stdio: 'inherit' }
  ),
  spawn(
    python(serverDir),
    ['-m', 'uvicorn', 'app.main:app', '--port', '4000', '--log-level', 'warning', '--reload'],
    { cwd: serverDir, stdio: 'inherit' }
  ),
];

const stopAll = () => {
  for (const child of children) {
    try {
      child.kill();
    } catch {
      /* already gone */
    }
  }
};

process.on('SIGINT', () => {
  stopAll();
  process.exit(0);
});
process.on('SIGTERM', () => {
  stopAll();
  process.exit(0);
});
process.on('exit', stopAll);

// If any process dies, take the rest down — half a stack only confuses.
const watch = (child) => {
  child.on('exit', (code) => {
    if (code !== null && code !== 0) {
      console.error(`\nA process exited with code ${code} — stopping the stack.\n`);
      stopAll();
      process.exit(code);
    }
  });
  return child;
};
children.forEach(watch);

const getJson = async (url, timeoutMs = 60_000) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch {
      /* not up yet */
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return null;
};

// Only into an empty catalogue: seed_demo.py truncates first, so doing this
// every start would throw away whatever was being worked on. Empty is the
// case worth automating — a fresh clone, or a database pytest just wiped.
const catalogue = await getJson('http://127.0.0.1:4000/products?limit=1');
if (catalogue === null) {
  console.error('\nServer never came up — skipping the seed.\n');
} else if (catalogue.items.length === 0) {
  console.log('→ empty catalogue, seeding demo data (about a minute)');
  // The seed places real orders against the two servers above, so it has to
  // run while they are alive — hence spawn, not execSync.
  await new Promise((resolve) => {
    const seed = spawn(python(serverDir), ['scripts/seed_demo.py'], {
      cwd: serverDir,
      stdio: 'inherit',
    });
    seed.on('exit', (code) => {
      if (code !== 0) console.error('\nSeeding failed — the app will be empty.\n');
      resolve();
    });
    seed.on('error', resolve);
  });
}

// One quoted string, not (cmd, args): shell:true concatenates args
// unquoted, and this path contains a space ("Project 4week").
children.push(
  watch(
    spawn(`"${path.join(appDir, 'node_modules', '.bin', 'v-miniapp-cli')}" dev`, {
      cwd: appDir,
      stdio: 'inherit',
      shell: true,
    })
  )
);
