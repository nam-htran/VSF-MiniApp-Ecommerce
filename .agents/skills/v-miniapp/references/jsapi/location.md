# Location APIs

APIs for location services.

---

## getLocation

**When to use:** Get current device location.

**Basic usage (async):**
```tsx
const location = await apisAsync.getLocation({
  type: 'gcj02'
})
// location.latitude - latitude
// location.longitude - longitude
```

**Key options:**
- `type`: `'wgs84' | 'gcj02'` - Coordinate system type

**Returns:**
- `latitude`: `number` - Latitude
- `longitude`: `number` - Longitude

**Note:** Requires location permission. User may be prompted to grant permission.
