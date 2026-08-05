# Scan QR API

API for QR code scanning.

---

## scan

**When to use:** Open QR code scanner.

**Basic usage (async):**
```tsx
const result = await apisAsync.scan({
  scanType: ['qrCode', 'barCode']
})
// result.result - scanned code string
```

**Key options:**
- `scanType`: `('qrCode' | 'barCode')[]` - Types of codes to scan

**Returns:**
- `result`: `string` - Scanned code content

**Note:** Opens native camera scanner. Requires camera permission.
