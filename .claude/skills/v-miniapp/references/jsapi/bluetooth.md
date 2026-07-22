# Bluetooth APIs

APIs for Bluetooth beacon discovery.

---

## startBeaconDiscovery

**When to use:** Start Bluetooth beacon discovery.

**Basic usage (async):**
```tsx
await apisAsync.startBeaconDiscovery({
  // beacon discovery options
})
```

**Key options:**
- Check API docs for beacon discovery configuration

**Note:** Requires Bluetooth permission. Use `onBeaconDiscovery` to listen for discovered beacons.

---

## stopBeaconDiscovery

**When to use:** Stop Bluetooth beacon discovery.

**Basic usage (async):**
```tsx
await apisAsync.stopBeaconDiscovery()
```

---

## getBeaconDiscoveryStatus

**When to use:** Get current beacon discovery status.

**Basic usage (async):**
```tsx
const status = await apisAsync.getBeaconDiscoveryStatus()
```

**Returns:** Discovery status information.

---

## onBeaconDiscovery

**When to use:** Listen for beacon discovery events.

**Basic usage:**
```tsx
apis.onBeaconDiscovery((beacons) => {
  // Handle discovered beacons
  console.log(beacons)
})
```

**Note:** Event listener. Call `offBeaconDiscovery()` to remove listener.

---

## offBeaconDiscovery

**When to use:** Remove beacon discovery event listener.

**Basic usage:**
```tsx
apis.offBeaconDiscovery()
```
