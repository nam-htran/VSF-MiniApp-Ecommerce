# Storage APIs

APIs for local storage operations.

---

## setStorage

**When to use:** Save data to local storage.

**Basic usage (async):**
```tsx
await apisAsync.setStorage({
  key: 'userName',
  data: 'John Doe'
})

// Store object
await apisAsync.setStorage({
  key: 'userData',
  data: { id: 1, name: 'John' }
})
```

**Key options:**
- `key`: `string` - Storage key
- `data`: `string | Record<string, any>` - Data to store

---

## getStorage

**When to use:** Retrieve data from local storage.

**Basic usage (async):**
```tsx
const data = await apisAsync.getStorage({
  key: 'userName'
})
```

**Key options:**
- `key`: `string` - Storage key

**Returns:** Stored data (string or object).

---

## removeStorage

**When to use:** Remove a specific key from storage.

**Basic usage (async):**
```tsx
await apisAsync.removeStorage({
  key: 'userName'
})
```

**Key options:**
- `key`: `string` - Storage key to remove

---

## clearStorage

**When to use:** Clear all local storage data.

**Basic usage (async):**
```tsx
await apisAsync.clearStorage()
```

**Note:** Removes all stored data. Use with caution.

---

## getStorageInfo

**When to use:** Get storage usage information.

**Basic usage (async):**
```tsx
const info = await apisAsync.getStorageInfo()
// info.keys - array of all keys
// info.currentSize - current storage size
// info.limitSize - storage limit
```

**Returns:**
- `keys`: Array of all storage keys
- `currentSize`: Current storage size in bytes
- `limitSize`: Maximum storage size in bytes
