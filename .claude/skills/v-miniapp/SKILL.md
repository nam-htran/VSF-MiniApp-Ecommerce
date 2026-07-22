---
name: v-miniapp
description: Create, run, debug, build, and deploy V Mini Apps with `@v-miniapp/cli`, and integrate runtime capabilities with `@v-miniapp/apis`. Use this skill whenever the user mentions mini-app setup, `v-miniapp-cli`, login, scaffolding, simulator/dev flow, deploy, or native capabilities like storage, scan QR, payment, location, camera, and app permissions, even if they do not explicitly name the packages.
---

# Overview

Use this skill for the end-to-end V Mini App workflow outside the dedicated `@v-miniapp/ui-react` UI layer.

This skill covers project bootstrap, CLI execution, auth/session expectations, build and deploy flow, and `@v-miniapp/apis` usage for native capabilities inside V-App. If the task is mainly about app shell structure, routing, localization, design tokens, or component composition, prefer the dedicated `v-miniapp-ui-react` skill.

# Process

## Phase 1: Identify the Request

- Treat requests mentioning "miniapp", "mini-app", "mini app", "V-MiniApp", or V-App mini-app development as V Mini App tasks.
- Read [User intent](./references/user-intent.md) when the phrasing is ambiguous.
- Decide whether the task is primarily:
  - CLI/setup/build/deploy work
  - Runtime capability work with `@v-miniapp/apis`
  - A mixed task that also needs the UI-focused skill

## Phase 2: Handle CLI and Project Lifecycle

### 2.1 Bootstrap and local development

- Follow [CLI guidelines](./references/ai-guidelines/cli.md) before running commands.
- Use `@v-miniapp/cli` for create, dev, build, deploy, login, and other lifecycle tasks.
- Prefer fully automated CLI flows; avoid leaving interactive prompts hanging.
- Confirm login/session requirements before create/dev/deploy operations.
- Follow [Basic setup](./references/basic-setup.md) for the standard dev/build/deploy flow and `app-config.json` expectations.

### 2.2 Deployment-aware implementation

- Keep `app-config.json` aligned with the app identity expected by V-App.
- Use the CLI build/deploy flow instead of inventing a custom packaging process.
- When setup tasks spill into UI architecture, hand off the UI-specific portion to the dedicated `ui-react` skill.

## Phase 3: Use Native Capabilities Correctly

- Follow [JSAPI guidelines](./references/ai-guidelines/jsapi.md) whenever code interacts with native features.
- Prefer APIs from `@v-miniapp/apis` over browser-native substitutes when the feature is provided by V-App.
- Verify API names, parameter shapes, async usage, and error handling against the matching reference.
- Match the requested capability to the correct API family: auth/open, storage, feedback, network, location, media, biometrics, bluetooth, payment, sharing, or QR scan.

## Phase 4: Validate the Result

- Confirm CLI commands and workflow assumptions match the documented `v-miniapp-cli` behavior.
- Confirm API calls match the documented `@v-miniapp/apis` contracts.
- Avoid manual workarounds for flows already handled by the SDK or CLI.
- If the task includes app routing, component composition, design tokens, or navigation UI, coordinate with the dedicated `v-miniapp-ui-react` skill.

# Reference Files

Use the bundled reference files under `packages/skills/mini-app/references/` and load only what the task needs.

## Core guidance

- [User intent](./references/user-intent.md) - how to recognize V Mini App requests.
- [CLI guidelines](./references/ai-guidelines/cli.md) - automation, login expectations, and non-interactive command handling.
- [JSAPI guidelines](./references/ai-guidelines/jsapi.md) - preferred API usage and verification checklist.
- [Basic setup](./references/basic-setup.md) - dev, build, deploy, and `app-config.json` essentials.

## CLI

- [CLI commands](./references/cli/commands.md) - available `v-miniapp-cli` commands and options.

## JSAPI

- [Open](./references/jsapi/open.md) - auth and app-opening flows.
- [Payment](./references/jsapi/payment.md) - payment method and payment initialization flows.
- [Storage](./references/jsapi/storage.md) - persistent mini-app storage APIs.
- [Network](./references/jsapi/network.md) - request APIs.
- [Feedback](./references/jsapi/feedback.md) - alerts, toasts, action sheets, and loading states.
- [Location](./references/jsapi/location.md) - location access.
- [Image](./references/jsapi/image.md) - image picker, preview, and compression.
- [File and network](./references/jsapi/file-network.md) - upload and download operations.
- [Basic](./references/jsapi/basic.md) - system info, settings, and exit flows.
- [Phone](./references/jsapi/phone.md) - phone call integration.
- [Biometrics](./references/jsapi/biometrics.md) - local auth and signature-related APIs.
- [Bluetooth](./references/jsapi/bluetooth.md) - beacon discovery and related APIs.
- [Share app](./references/jsapi/share-app.md) - app sharing flows.
- [Scan QR](./references/jsapi/scan-qr.md) - QR code scan support.
