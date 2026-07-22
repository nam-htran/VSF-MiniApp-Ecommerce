# Biometrics APIs

APIs for biometric authentication (fingerprint, face ID).

---

## bioMetrics.isSupported

**When to use:** Check if biometric authentication is supported on device.

**Basic usage (async):**
```tsx
const supported = await apisAsync.bioMetrics.isSupported()
// supported - boolean
```

**Returns:** `boolean` - `true` if biometrics is supported.

---

## bioMetrics.keyExists

**When to use:** Check if a biometric key exists for the given key alias.

**Basic usage (async):**
```tsx
const exists = await apisAsync.bioMetrics.keyExists({
  keyAlias: 'user_key'
})
```

**Key options:**
- `keyAlias`: `string` - Key alias to check

**Returns:** `boolean` - `true` if key exists.

---

## bioMetrics.createKey

**When to use:** Create a new biometric key.

**Basic usage (async):**
```tsx
await apisAsync.bioMetrics.createKey({
  keyAlias: 'user_key'
})
```

**Key options:**
- `keyAlias`: `string` - Unique key alias

**Note:** User will be prompted for biometric authentication during key creation.

---

## bioMetrics.localAuth

**When to use:** Authenticate using biometrics.

**Basic usage (async):**
```tsx
const result = await apisAsync.bioMetrics.localAuth({
  keyAlias: 'user_key'
})
// result - authentication result
```

**Key options:**
- `keyAlias`: `string` - Key alias to use for authentication

**Returns:** Authentication result object.

---

## bioMetrics.createSignature

**When to use:** Create a signature using biometric key.

**Basic usage (async):**
```tsx
const signature = await apisAsync.bioMetrics.createSignature({
  keyAlias: 'user_key',
  data: 'data_to_sign'
})
```

**Key options:**
- `keyAlias`: `string` - Key alias
- `data`: `string` - Data to sign

**Returns:** Signature string.

---

## bioMetrics.deleteKey

**When to use:** Delete a biometric key.

**Basic usage (async):**
```tsx
await apisAsync.bioMetrics.deleteKey({
  keyAlias: 'user_key'
})
```

**Key options:**
- `keyAlias`: `string` - Key alias to delete
