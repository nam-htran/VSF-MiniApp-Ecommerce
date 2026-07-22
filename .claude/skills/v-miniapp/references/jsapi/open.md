# Open APIs

APIs for authentication, user info, and opening external apps.

---

## getAuthCode

**When to use:** Get authentication code for user login/authorization.

**Import:** `import { apis } from '@v-miniapp/apis'` or `import { apisAsync } from '@v-miniapp/apis'`

**Basic usage (async):**
```tsx
const result = await apisAsync.getAuthCode({
  scopes: ['profile', 'phone', 'email']
})
// result.authCode - auth code string
// result.authSuccessScopes - granted scopes
// result.authErrorScopes - failed scopes with reasons
```

**Key options:**
- `scopes`: `('profile' | 'phone' | 'email')[]` - Requested permission scopes

**Returns:**
- `authCode`: Authentication code string
- `authSuccessScopes`: Array of successfully granted scopes
- `authErrorScopes`: Object with failed scopes and error messages

---

## getUserInfo

**When to use:** Get current user information (avatar, name, gender, date of birth).

**Basic usage (async):**
```tsx
const userInfo = await apisAsync.getUserInfo()
// userInfo.avatar - avatar URL
// userInfo.name - user name
// userInfo.gender - gender
// userInfo.dateOfBirth - date of birth
```

**Returns:**
- `avatar`: Avatar image URL (optional)
- `name`: User name
- `gender`: Gender (optional)
- `dateOfBirth`: Date of birth string (optional)

**Note:** Requires user permission. May need to request `profile` scope via `getAuthCode` first.

---

## openNativeAppStore

**When to use:** Open native app store (for app updates, ratings).

**Basic usage (async):**
```tsx
await apisAsync.openNativeStore()
```

**Note:** Opens the native app store page for the current app.
