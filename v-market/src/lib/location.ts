import { apisAsync } from '@v-miniapp/apis';

/**
 * The platform's getLocation returns raw GPS — latitude and longitude,
 * no street address and no reverse geocoding. So this pins a delivery
 * point for the courier; the human-readable address is still typed.
 *
 * Outside V-App (a plain browser tab, a test) the bridge is absent and
 * the call would throw on property access, so callers treat "no location"
 * as a soft failure and fall back to the manual address.
 */
export type GeoPin = { latitude: number; longitude: number };

const hasBridge = () =>
  typeof window !== 'undefined' && Boolean((window as { vsf?: unknown }).vsf);

export async function getCurrentLocation(): Promise<GeoPin> {
  if (!hasBridge()) {
    throw new Error('Vị trí chỉ khả dụng trong ứng dụng V-App');
  }
  // type: 1 asks for high accuracy; the platform shows its own permission
  // prompt the first time and remembers the answer.
  const { latitude, longitude } = await apisAsync.getLocation({ type: 1 });
  return { latitude, longitude };
}

export const formatPin = (pin: GeoPin) =>
  `${pin.latitude.toFixed(5)}, ${pin.longitude.toFixed(5)}`;
