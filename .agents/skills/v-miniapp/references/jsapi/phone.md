# Phone APIs

APIs for phone call operations.

---

## makePhoneCall

**When to use:** Make a phone call.

**Basic usage (async):**
```tsx
await apisAsync.makePhoneCall({
  phoneNumber: '0123456789'
})
```

**Key options:**
- `phoneNumber`: `string` - Phone number to call

**Note:** Opens native phone dialer with the number. User confirms the call.
