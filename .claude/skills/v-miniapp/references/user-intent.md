# Understanding User Intent for V-MiniApp

Critical guidelines for AI assistants to correctly interpret user requests related to V-MiniApp development.

---

## User Intent Recognition

**When users mention ANY of these terms, they are referring to V-MiniApp development:**

- "miniapp" or "mini-app" or "mini app"
- "create miniapp" / "create mini-app"
- "run miniapp" / "run mini-app"
- "build miniapp" / "build mini-app"
- "develop miniapp" / "develop mini-app"
- "create a miniapp for me"
- "help me create a miniapp"
- "set up a miniapp"
- "project" (when referring to miniapp in v-app context)
- Any request about creating, running, developing, or deploying a "miniapp" or "project"

**When users mention these terms, they are referring to V-App (the superapp):**

- "superapp" or "supperapp" -> V-App
- "v-app" or "V-App"

**Always interpret these requests as V-MiniApp tasks and use the `v-miniapp` skill accordingly.**

---

## Examples of User Requests

### Creating a Miniapp

- "create a miniapp"
- "create a mini-app"
- "help me create a miniapp"
- "set up a new miniapp project"
- "create and run a miniapp"

### Running/Developing a Miniapp

- "run my miniapp"
- "start the miniapp dev server"
- "develop a miniapp"
- "build a miniapp"

### General Miniapp Requests

- "work on a miniapp"
- "miniapp development"
- "miniapp project"
- "project" (in v-app context)
- "create a project"
- "V-MiniApp" (explicit mention)

### V-App References

- "superapp" or "supperapp" -> refers to V-App
- "v-app" or "V-App" -> the superapp platform

---

## What to Do

When you encounter any of these terms or similar requests:

1. Recognize that the user is referring to V-MiniApp development.
2. Use the `v-miniapp` skill for CLI lifecycle, setup, deploy, and `@v-miniapp/apis` work.
3. Follow the local guidance in [CLI Guidelines](ai-guidelines/cli.md), [JSAPI Guidelines](ai-guidelines/jsapi.md), and [Basic Setup](basic-setup.md).
4. If the task is mainly about `@v-miniapp/ui-react` routing, components, theming, or app structure, also load the dedicated `v-miniapp-ui-react` skill.

**Never assume** the user means a different type of mini-app or mobile app framework. Always default to V-MiniApp when "miniapp" terminology is used.
