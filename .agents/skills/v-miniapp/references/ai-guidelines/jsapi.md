# JSAPI Guidelines

Critical guidelines for AI assistants when working with JavaScript APIs (`@v-miniapp/apis`) in V-MiniApp projects.

---

## JSAPI Usage Guidelines

**CRITICAL:** When interacting with V-App native features, **ALWAYS** use APIs from `@v-miniapp/apis` instead of direct native calls or custom implementations.

### API Priority Rules

1. **Always prefer @v-miniapp/apis** over direct native calls:

   - Use `apisAsync.alert()` instead of native `alert()`
   - Use `apisAsync.getStorage()` instead of `localStorage` directly
   - Use `apisAsync.request()` for network calls
   - Use `apisAsync.chooseImage()` for image selection
   - Use `apisAsync.getLocation()` for location services
   - Use `apisAsync.scan()` for QR code scanning
   - Use `apisAsync.initPayment()` for payment processing

2. **Before creating custom implementations**, check if an API exists in `@v-miniapp/apis`:

   - Review API references in `references/jsapi/` directory
   - Check available API groups: Open, Payment, Storage, Network, Feedback, Location, Image, File & Network, Basic, Phone, Biometrics, Bluetooth, Share App, Scan QR
   - Use the appropriate API from the library

3. **Import pattern:**

   ```tsx
   import { apisAsync } from '@v-miniapp/apis'
   // or
   import apis from '@v-miniapp/apis'
   ```

4. **Async vs Sync:**

   - Prefer `apisAsync` for async/await pattern (recommended)
   - Use `apis` (sync) only when needed for callback-based patterns
   - Use `apisSync` for direct synchronous calls (rarely needed)

---

## API Usage Examples

**Do not use native APIs:**

```tsx
// Bad: Using native alert
alert('Hello')

// Bad: Using localStorage directly
localStorage.setItem('key', 'value')

// Bad: Using fetch directly
fetch('/api/data')
```

**Use @v-miniapp/apis:**

```tsx
// Good: Using apisAsync.alert
await apisAsync.alert({
  title: 'Hello',
  content: 'World',
  buttonText: 'OK',
})

// Good: Using apisAsync.getStorage
const data = await apisAsync.getStorage({ key: 'userData' })

// Good: Using apisAsync.request
const response = await apisAsync.request({
  url: '/api/data',
  method: 'GET',
})
```

---

## Verify API Usage After Code Generation

**CRITICAL:** After generating code, always verify that API calls are correct and complete by checking the API references.

**Verification checklist:**

1. **Check API method names:**

   - Verify API method names match exactly with the documentation
   - Check API references in `references/jsapi/` directory
   - Ensure method names are spelled correctly (case-sensitive)

2. **Verify API parameters:**

   - Confirm parameter structure matches the API documentation
   - Check required vs optional parameters
   - Verify parameter types and formats

3. **Error handling:**
   - Always wrap API calls in try-catch blocks when using `apisAsync`
   - Handle errors appropriately based on API documentation
   - Provide user feedback for API errors

**Remember:** Always cross-reference generated code with API documentation to ensure API calls are valid and complete. When in doubt, check the API references.

---

## API Reference Quick Lookup

When implementing features that interact with V-App, check these API groups first:

- **Open:** `getAuthCode`, `getUserInfo`, `openNativeStore` - Authentication and app opening
- **Payment:** `showPaymentMethod`, `getDefaultPaymentMethod`, `initPayment` - Payment processing
- **Storage:** `getStorageInfo`, `setStorage`, `getStorage`, `removeStorage`, `clearStorage` - Local storage
- **Network:** `request` - Network requests
- **Feedback:** `alert`, `confirm`, `prompt`, `showToast`, `showLoading`, `hideLoading`, `showActionSheet` - User feedback
- **Location:** `getLocation` - Location services
- **Image:** `chooseImage`, `previewImage`, `compressImage` - Image operations
- **File & Network:** `downloadFile`, `uploadFile` - File operations
- **Basic:** `getSystemInfo`, `getSetting`, `exitMiniApp` - System information
- **Phone:** `makePhoneCall` - Phone calls
- **Biometrics:** `isSupported`, `localAuth`, `keyExists`, `createKey`, `deleteKey`, `createSignature` - Biometric authentication
- **Bluetooth:** `startBeaconDiscovery`, `stopBeaconDiscovery`, `getBeaconDiscoveryStatus`, `onBeaconDiscovery`, `offBeaconDiscovery` - Bluetooth beacons
- **Share App:** `shareApp` - App sharing
- **Scan QR:** `scan` - QR code scanning

See [JSAPI References](../jsapi/) for detailed usage of each API group.
