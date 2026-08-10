/**
 * `npm run dev` — the whole stack in one terminal:
 *   1. requires Docker (Postgres lives there)
 *   2. creates the Python venvs on first run if they are missing
 *   3. docker compose up -d --wait
 *   4. alembic upgrade head
 *   5. mock-openAPI :4001, server :4000
 *   6. seeds the demo data, but only when there is none
 *   7. MiniApp dev server
 *
 * Each step below is one function, in that order; `main` at the bottom is the
 * whole script. Ctrl+C stops everything. `npm run dev:app` runs the MiniApp
 * alone.
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
const onWindows = process.platform === 'win32';

const python = (dir) =>
  path.join(dir, onWindows ? '.venv/Scripts/python.exe' : '.venv/bin/python');

// One shape for everything this script says, so its own output stays apart
// from the four children's. `step` marks a wait the developer would otherwise
// read as a hang; anything the stack itself already announces goes unsaid.
//
// The conventions are the usual ones (clig.dev), and match server/app/console.py
// so the two halves of a start read as one program: status on stderr, colour
// only on an interactive terminal, NO_COLOR and TERM=dumb honoured. Sharing
// stderr with the backend also keeps the ordering honest — two streams into
// one terminal interleave by flush order, not by when they were written.
const colour =
  Boolean(process.stderr.isTTY) && !process.env.NO_COLOR && process.env.TERM !== 'dumb';
const paint = (code, text) => (colour ? `\x1b[${code}m${text}\x1b[0m` : text);

const step = (message) => console.error(`${paint('36', '→')} ${message}`);
const warn = (message) => console.error(`\n${paint('31', '✘')} ${message}\n`);
const fail = (message) => {
  warn(message);
  process.exit(1);
};

// Every child lands here so Ctrl+C reaches the ones spawned later too.
const children = [];
const stopAll = () => {
  for (const child of children) {
    try {
      child.kill();
    } catch {
      /* already gone */
    }
  }
};

// If any process dies, take the rest down — half a stack only confuses.
const track = (child) => {
  children.push(child);
  child.on('exit', (code) => {
    if (code !== null && code !== 0) {
      warn(`A process exited with code ${code} — stopping the stack.`);
      stopAll();
      process.exit(code);
    }
  });
  return child;
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

// 1. Docker first — everything else depends on Postgres. "docker info" fails
// three different ways, and each wants different advice: the old code called
// all of them "Docker is not running", which on WSL (daemon up, socket
// permission denied) sent people to restart a Docker Desktop they may not
// even use.
const requireDocker = () => {
  const probe = spawnSync('docker', ['info'], { encoding: 'utf8' });
  if (probe.error?.code === 'ENOENT') {
    fail('Docker is not installed — install Docker first, then run `npm run dev` again.');
  }
  if (probe.status === 0) return;

  const message = `${probe.stdout ?? ''}${probe.stderr ?? ''}`;
  if (/permission denied/i.test(message)) {
    fail(
      'Docker is running but this user cannot reach its socket.\n' +
        '  sudo usermod -aG docker $USER\n' +
        (isWSL
          ? 'then run `wsl --shutdown` from Windows and reopen WSL (group membership is read at login).'
          : 'then log out and back in (group membership is read at login).')
    );
  } else if (isWSL) {
    fail(
      'Docker daemon is not responding. Start it with:\n' +
        '  sudo service docker start   # or: sudo systemctl start docker\n' +
        'If you use Docker Desktop, enable its WSL integration for this distro instead.'
    );
  } else {
    fail('Docker is not running. Start Docker Desktop, wait for it to go green, then run `npm run dev` again.');
  }
};

// 2. First run on a fresh clone: build the venvs instead of complaining.
const findBasePython = () => {
  for (const candidate of onWindows ? ['py', 'python'] : ['python3', 'python']) {
    try {
      execSync(`${candidate} --version`, { stdio: 'ignore' });
      return candidate;
    } catch {
      /* try the next one */
    }
  }
  return fail('No Python found on PATH — install Python 3.12+ first.');
};

const ensureVenvs = () => {
  const missing = [serverDir, mockDir].filter((dir) => !existsSync(python(dir)));
  if (missing.length === 0) return;

  const basePython = findBasePython();
  for (const dir of missing) {
    // pip prints plenty on its own, but only after a silent `venv` call and
    // without naming which of the two directories it is working in.
    step(`creating venv in ${path.basename(dir)} (first run)`);
    execSync(`${basePython} -m venv .venv`, { cwd: dir, stdio: 'inherit' });
    execSync(`"${python(dir)}" -m pip install -r requirements.txt`, {
      cwd: dir,
      stdio: 'inherit',
      shell: true,
    });
  }
};

// 3 + 4. Both announce themselves through stdio: compose names each container
// and its health, alembic logs every revision it applies.
const startDatabase = () =>
  execSync('docker compose up -d --wait', { cwd: root, stdio: 'inherit' });

// The app no longer creates its own tables; migrations own the schema.
const migrate = () =>
  execSync(`"${python(serverDir)}" -m alembic upgrade head`, {
    cwd: serverDir,
    stdio: 'inherit',
    shell: true,
  });

// 5. --reload on both Python servers, quiet logs so the MiniApp CLI's output
// stays readable. On a Windows drive, uvicorn's watcher (watchfiles) never
// sees edits — inotify events don't cross the 9p mount — so hot reload
// silently stops working. Polling is the only thing that does see them.
// The AI stack also announces itself at length on every start — transformers'
// info chatter, the Hub's "you are unauthenticated" notice, and a
// FutureWarning that sentence-transformers triggers inside transformers. None
// of it is actionable here and all of it buries the startup progress, so
// quieten it for the two uvicorn children only. Errors still print, and the
// warning filter names the one module that emits it rather than dropping
// FutureWarning everywhere — a deprecation in this project's own code must
// still show.
// The HuggingFace download bar goes too. It only ever covered the Jina
// encoder — the decoder checkpoint is one torch.load with no fraction to
// report — and a bar on one of the two steps made the other look stuck.
// app/console.py times both instead, which is the same information in the
// same shape.
const pyEnv = {
  ...process.env,
  ...(onWindowsMount ? { WATCHFILES_FORCE_POLLING: 'true' } : {}),
  TRANSFORMERS_VERBOSITY: 'error',
  HF_HUB_VERBOSITY: 'error',
  HF_HUB_DISABLE_PROGRESS_BARS: '1',
  PYTHONWARNINGS: 'ignore::FutureWarning:transformers.modeling_attn_mask_utils',
};

const startBackends = () => {
  const uvicorn = (dir, target, port) =>
    track(
      spawn(
        python(dir),
        ['-m', 'uvicorn', target, '--port', String(port), '--log-level', 'warning', '--reload'],
        { cwd: dir, stdio: 'inherit', env: pyEnv }
      )
    );
  uvicorn(mockDir, 'main:app', 4001);
  uvicorn(serverDir, 'app.main:app', 4000);
};

// 6. Only into an empty catalogue: seed_demo.py truncates first, so doing this
// every start would throw away whatever was being worked on. Empty is the
// case worth automating — a fresh clone, or a database pytest just wiped.
const getJson = async (url, timeoutMs) => {
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

const seedIfEmpty = async () => {
  // The wait is minutes, not seconds: the backend loads the Transformer
  // checkpoint and the Jina encoder inside its lifespan, so it answers nothing
  // at all until both are in memory — and the checkpoint is read across the 9p
  // mount. A 60s guess expired mid-load and skipped the seed, which only shows
  // up later as an app with an empty catalogue.
  step('waiting for the backend to load its models (first start: a few minutes)');
  const catalogue = await getJson('http://127.0.0.1:4000/products?limit=1', 300_000);

  if (catalogue === null) {
    warn(
      'Backend still silent after 5 minutes — skipping the seed.\n' +
        'If it comes up later, seed by hand:\n' +
        '  cd server\n' +
        `  ${onWindows ? '.venv\\Scripts\\python' : '.venv/bin/python'} scripts/seed_demo.py`
    );
    return;
  }
  if (catalogue.items.length > 0) return;

  step('empty catalogue, seeding demo data (about a minute)');
  // The seed places real orders against the two servers above, so it has to
  // run while they are alive — hence spawn, not execSync.
  await new Promise((resolve) => {
    const seed = spawn(python(serverDir), ['scripts/seed_demo.py'], {
      cwd: serverDir,
      stdio: 'inherit',
    });
    seed.on('exit', (code) => {
      if (code !== 0) warn('Seeding failed — the app will be empty.');
      resolve();
    });
    seed.on('error', resolve);
  });
};

// 7. `v-miniapp-cli dev` refuses to start without a V-ID token. That login
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
const hasRealLogin = () => {
  const credentialsFile = path.join(os.homedir(), '.v-miniapp', 'credentials.json');
  if (!existsSync(credentialsFile)) return false;
  try {
    return readFileSync(credentialsFile, 'utf8').trim().length > 0;
  } catch {
    return false;
  }
};

const miniAppEnv = () => {
  if (process.env.MINIAPP_CLI_TOKEN || hasRealLogin()) return { ...process.env };

  const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
  const tenYears = 10 * 365 * 24 * 60 * 60;
  return {
    ...process.env,
    MINIAPP_CLI_TOKEN: [
      b64url({ alg: 'none', typ: 'JWT' }),
      b64url({ sub: 'local-dev', exp: Math.floor(Date.now() / 1000) + tenYears }),
      'local-dev',
    ].join('.'),
  };
};

// One quoted string, not (cmd, args): shell:true concatenates args
// unquoted, and this path contains a space ("Project 4week").
// --no-open: in WSL there is no browser to launch, and the failed launch is
// noise — the CLI prints the URL to open by hand either way.
const startMiniApp = () =>
  track(
    spawn(`"${path.join(appDir, 'node_modules', '.bin', 'v-miniapp-cli')}" dev --no-open`, {
      cwd: appDir,
      stdio: 'inherit',
      shell: true,
      env: miniAppEnv(),
    })
  );

const main = async () => {
  requireDocker();
  ensureVenvs();
  startDatabase();
  migrate();
  startBackends();
  await seedIfEmpty();
  startMiniApp();
};

await main();
