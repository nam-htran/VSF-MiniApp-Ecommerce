# V Mini App Skill

Create, run, build, and deploy V Mini Apps with `@v-miniapp/cli` and integrate native capabilities with `@v-miniapp/apis`.

## Features

- **CLI Tooling** - Scaffold, dev server, build, and deploy with `@v-miniapp/cli`
- **JavaScript APIs** - Auth, storage, payment, location, camera, QR scan, biometrics, and more via `@v-miniapp/apis`
- **Native Capabilities** - Access device features like phone calls, file upload/download, Bluetooth beacons
- **Non-Interactive CLI** - AI-optimized guidelines for fully automated command execution
- **Dev & Deploy Flow** - Hot reload dev server, production build, and one-command deploy to V-App

## Installation

### Option 1: Using skills CLI (Recommended)

```bash
# Install to current project
npx skills add https://github.com/v-open-platform/v-mini-app-skills

# Install globally
npx skills add https://github.com/v-open-platform/v-mini-app-skills -g

# Install for specific agent
npx skills add https://github.com/v-open-platform/v-mini-app-skills -a claude-code
```

### Option 2: Manual Installation

**For Claude Code:**

```bash
git clone <repo-url> v-mini-app-skills
cp -r v-mini-app-skills/skills/v-miniapp ~/.claude/skills/
```

**For Project-level:**

```bash
mkdir -p .claude/skills
cp -r v-mini-app-skills/skills/v-miniapp .claude/skills/
```

## Supported Agents

| Agent          | Skills Directory                         |
| -------------- | ---------------------------------------- |
| Claude Code    | `~/.claude/skills/` or `.claude/skills/` |
| Cursor         | `~/.cursor/skills/` or `.cursor/skills/` |
| OpenCode       | `~/.opencode/skill/`                     |
| GitHub Copilot | `.github/copilot/skills/`                |
| Windsurf       | `~/.windsurf/skills/`                    |

## Usage

Once installed, the skill activates automatically when you:

- Create or scaffold new V Mini Apps
- Run CLI commands (`v-miniapp-cli dev`, `build`, `deploy`)
- Use native device APIs via `@v-miniapp/apis`
- Integrate payments, storage, location, or camera
- Work with auth flows and user permissions

### Quick Start

```bash
npm install -g @v-miniapp/cli
v-miniapp-cli login
v-miniapp-cli create my-app && cd my-app && v-miniapp-cli dev
```

### Example Prompts

- "Create a new V Mini App with Tailwind CSS"
- "Add QR code scanning to my mini app"
- "Integrate payment flow with `@v-miniapp/apis`"
- "Deploy my mini app to V-App"
- "Add biometric authentication to my app"

## Skill Structure

```
v-miniapp/
├── SKILL.md                          # Main skill file
└── references/
    ├── user-intent.md                # Request recognition guide
    ├── basic-setup.md                # Dev, build, deploy & app config
    ├── ai-guidelines/
    │   ├── cli.md                    # CLI automation guidelines
    │   └── jsapi.md                  # JSAPI usage guidelines
    ├── cli/
    │   └── commands.md               # Full CLI command reference
    └── jsapi/
        ├── basic.md                  # System info & exit
        ├── open.md                   # Auth & app opening
        ├── payment.md                # Payment processing
        ├── storage.md                # Local storage
        ├── network.md                # HTTP requests
        ├── feedback.md               # Dialogs, toasts, loading
        ├── location.md               # Geolocation
        ├── image.md                  # Image picker & compression
        ├── file-network.md           # File upload/download
        ├── phone.md                  # Phone calls
        ├── biometrics.md             # Fingerprint/Face ID
        ├── bluetooth.md              # Beacon discovery
        ├── scan-qr.md               # QR code scanning
        └── share-app.md             # App sharing
```

## Related Skills

| Skill                  | Purpose                                                                   |
| ---------------------- | ------------------------------------------------------------------------- |
| **v-miniapp-ui-react** | UI components, routing, theming, design tokens with `@v-miniapp/ui-react` |
| **ai-app**             | MCP-based AI apps with `@v-miniapp/ai` server/web/apis modules            |

## Resources

- [Developer](https://developer.v-app.vn/)
- [V-App](https://v-app.vn/)
- [Agent Skills Specification](https://agentskills.io/specification)

## License

MIT
