# CLI Commands

Command-line interface commands from `@v-miniapp/cli`.

---

## Setup Commands

### create

**When to use:** Create a new V-MiniApp project from template.

**Usage:**

```bash
v-miniapp-cli create [project-name]
```

**Options:**

- `--css <framework>`: CSS framework (`tailwind`, `none`)
- `--pm <manager>`: Package manager (`pnpm`, `npm`, `yarn`)
- `--install`: Install dependencies automatically
- `--token <token>`: Use access token for authentication (for login and deploy, alternative to `login` command) for authentication (for login and deploy, alternative to `login` command)

**Note:** Requires authentication (either `login` or `--token`). Prompts for framework, CSS, and package manager if not provided via options.

---

### list (ls)

**When to use:** List all available project templates.

**Usage:**

```bash
v-miniapp-cli list
# or
v-miniapp-cli ls
```

---

## Development Commands

### dev

**When to use:** Start local development server with hot reload.

**Usage:**

```bash
v-miniapp-cli dev
```

**Options:**

- `--host <host>`: Host for runtime dev server (default: `localhost`)
- `--host-port <number>`: Port for runtime dev server
- `--remote-host <host>`: Host for mini app dev server (default: `localhost`)
- `--remote-port <number>`: Port for mini app dev server
- `--no-frame`: Run dev without frame
- `--no-open`: Do not auto open browser
- `--config <path>`: Path to vite config file
- `--no-toolbar`: Hide toolbar in simulator
- `--framework-url <url>`: Override framework runtime script URL (non-production)
- `--simulator-url <url>`: Override simulator CDN URL (non-production)
- `--token <token>`: Use access token for authentication (for login and deploy, alternative to `login` command)

**Note:**

- Mini App server runs on port range `8080-8999`
- Simulator server runs on port range `3000-3999`
- Requires authentication (either `login` or `--token`) for authenticated features

---

## Build & Deploy Commands

### build

**When to use:** Compile and bundle the project for production.

**Usage:**

```bash
v-miniapp-cli build
```

**Options:**

- `--config <path>`: Path to vite config file
- `--framework-url <url>`: Override framework runtime script URL (non-production)
- `--token <token>`: Use access token for authentication (for login and deploy, alternative to `login` command)

**Output:** Production bundle in `dist/` directory.

---

### deploy

**When to use:** Deploy the project to V-App platform.

**Usage:**

```bash
v-miniapp-cli deploy
```

**Options:**

- `--tool <tool>`: Deploy tool (`cli`, `extension`, default: `cli`)
- `--no-verify`: Deploy without scanning the project
- `--clean-framework`: Remove framework runtime script
- `--framework-url <url>`: Override framework runtime script URL (non-production)
- `--token <token>`: Use access token for authentication (for login and deploy, alternative to `login` command) for authentication (for login and deploy, alternative to `login` command)

**Process:**

1. Validates version in `package.json` and `app-config.json`
2. Runs `build` automatically if needed
3. Packages source and `dist` (respects `.gitignore`)
4. Uploads to V-App

**Note:** Requires authentication (either `login` or `--token`). Manage versions in [Dev Center](https://console.v-app.vn/).

---

## Authentication Commands

### login

**When to use:** Login with V-ID for authenticated CLI commands.

**Usage:**

```bash
v-miniapp-cli login
```

**Note:** Required before `create`, `dev`, and `deploy` commands. Alternatively, use `--token <token>` option with commands for authentication (works for login and deploy operations).

---

### logout

**When to use:** Clear local credentials and logout.

**Usage:**

```bash
v-miniapp-cli logout
```

---

## Utility Commands

### healthcheck (health)

**When to use:** Verify the status of V-App system services.

**Usage:**

```bash
v-miniapp-cli healthcheck
# or
v-miniapp-cli health
```

**Checks:** Connection status to V-App services (Auth, API, Web).

---

### version-check (vc)

**When to use:** Check for CLI updates and new releases.

**Usage:**

```bash
v-miniapp-cli version-check
# or
v-miniapp-cli vc
```

**Note:** Compares current version with latest NPM version and minimum required version from system.

---

## Common Workflows

**Initial setup:**

```bash
v-miniapp-cli login
v-miniapp-cli create my-app
cd my-app
v-miniapp-cli dev
```

**Build and deploy:**

```bash
v-miniapp-cli build
v-miniapp-cli deploy
```

**Using token for authentication:**

```bash
# Use token instead of login (works for login and deploy operations)
v-miniapp-cli create my-app --token <your-token>
v-miniapp-cli dev --token <your-token>
v-miniapp-cli deploy --token <your-token>
```

**Note:** The `--token` option provides authentication for both login and deploy operations, eliminating the need to run `login` command separately.
