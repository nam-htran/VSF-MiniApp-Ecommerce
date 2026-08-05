# Basic APIs

Basic system and app information APIs.

---

## getSystemInfo

**When to use:** Get device and system information.

**Basic usage (async):**

```tsx
const info = await apisAsync.getSystemInfo()
// info.platform - platform name
// info.system - OS version
// info.version - app version
// info.screenWidth - screen width
// info.screenHeight - screen height
```

**Returns:** System information object with platform, OS version, screen dimensions, etc.

---

## getSetting

**When to use:** Get user's authorization settings for various APIs.

**Basic usage (async):**

```tsx
const settings = await apisAsync.getSetting()
// settings.authSetting - authorization settings object
```

**Returns:** Authorization settings for location, camera, album, etc.

---

## exitMiniapp

**When to use:** Exit/close the mini-app.

**Basic usage (async):**

```tsx
await apisAsync.exitMiniApp()
```

**Note:** Closes the mini-app and returns to V-App.
