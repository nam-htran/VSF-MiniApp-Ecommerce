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
import { execSync, spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(appDir, '..');
const serverDir = path.join(root, 'server');
const mockDir = path.join(root, 'mock-openAPI');

// WSL and a project living on a Windows drive (/mnt/*) each change what the
// right thing to do is below — different Docker advice, and file-watching
// that inotify cannot deliver across the 9p mount.
const isWSL =
  process.platform === 'linux' &&
  (/microsoft/i.test(os.release()) || Boolean(process.env.WSL_DISTRO_NAME));
const onWindowsMount = root.startsWith('/mnt/');

const python = (dir) =>
  path.join(
    dir,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
  );

// Docker first — everything else depends on Postgres. "docker info" fails
// three different ways, and each wants different advice: the old code called
// all of them "Docker is not running", which on WSL (daemon up, socket
// permission denied) sent people to restart a Docker Desktop they may not
// even use.
const probe = spawnSync('docker', ['info'], { encoding: 'utf8' });
if (probe.error?.code === 'ENOENT') {
  console.error('\nDocker is not installed — install Docker first, then run `npm run dev` again.\n');
  process.exit(1);
} else if (probe.status !== 0) {
  const message = `${probe.stdout ?? ''}${probe.stderr ?? ''}`;
  if (/permission denied/i.test(message)) {
    console.error(
      '\nDocker is running but this user cannot reach its socket.\n' +
        '  sudo usermod -aG docker $USER\n' +
        (isWSL
          ? 'then run `wsl --shutdown` from Windows and reopen WSL (group membership is read at login).\n'
          : 'then log out and back in (group membership is read at login).\n')
    );
  } else if (isWSL) {
    console.error(
      '\nDocker daemon is not responding. Start it with:\n' +
        '  sudo service docker start   # or: sudo systemctl start docker\n' +
        'If you use Docker Desktop, enable its WSL integration for this distro instead.\n'
    );
  } else {
    console.error(
      '\nDocker is not running. Start Docker Desktop, wait for it to go green, then run `npm run dev` again.\n'
    );
  }
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
// stays readable. On a Windows drive, uvicorn's watcher (watchfiles) never
// sees edits — inotify events don't cross the 9p mount — so hot reload
// silently stops working. Polling is the only thing that does see them.
const pyEnv = onWindowsMount
  ? { ...process.env, WATCHFILES_FORCE_POLLING: 'true' }
  : process.env;
if (onWindowsMount) {
  console.log('→ project is on a Windows drive — enabling polling so backend hot reload works');
}
const children = [
  spawn(
    python(mockDir),
    ['-m', 'uvicorn', 'main:app', '--port', '4001', '--log-level', 'warning', '--reload'],
    { cwd: mockDir, stdio: 'inherit', env: pyEnv }
  ),
  spawn(
    python(serverDir),
    ['-m', 'uvicorn', 'app.main:app', '--port', '4000', '--log-level', 'warning', '--reload'],
    { cwd: serverDir, stdio: 'inherit', env: pyEnv }
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

// `v-miniapp-cli dev` refuses to start without a V-ID token. That login
// needs a working Vingroup account and DevCenter access this project does
// not have — the same gap that `mock-openAPI` exists to fill for the
// runtime. But `dev` only checks that a token is *present and unexpired*
// (client-side: it parses the JWT's `exp`, it does not verify the
// signature or call the server), so a locally-minted stand-in gets the
// simulator running. It buys nothing beyond that: `deploy` hits the real
// server, which rejects it. This is the CLI equivalent of the mock.
//
// A real login always wins: only mint the stand-in when there is neither a
// stored credential nor a token the developer set themselves.
const cliEnv = { ...process.env };
const credentialsFile = path.join(os.homedir(), '.v-miniapp', 'credentials.json');
const hasRealLogin = (() => {
  if (!existsSync(credentialsFile)) return false;
  try {
    return readFileSync(credentialsFile, 'utf8').trim().length > 0;
  } catch {
    return false;
  }
})();
if (!process.env.MINIAPP_CLI_TOKEN && !hasRealLogin) {
  const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
  const tenYears = 10 * 365 * 24 * 60 * 60;
  cliEnv.MINIAPP_CLI_TOKEN = [
    b64url({ alg: 'none', typ: 'JWT' }),
    b64url({ sub: 'local-dev', exp: Math.floor(Date.now() / 1000) + tenYears }),
    'local-dev',
  ].join('.');
  console.log(
    '→ no V-ID login found — using a local stand-in token so the simulator can start\n' +
      '  (local only; `npm run login` + a real account are still needed to deploy)'
  );
}

// One quoted string, not (cmd, args): shell:true concatenates args
// unquoted, and this path contains a space ("Project 4week").
// --no-open: in WSL there is no browser to launch, and the failed launch is
// noise — the CLI prints the URL to open by hand either way.
children.push(
  watch(
    spawn(`"${path.join(appDir, 'node_modules', '.bin', 'v-miniapp-cli')}" dev --no-open`, {
      cwd: appDir,
      stdio: 'inherit',
      shell: true,
      env: cliEnv,
    })
  )
);
