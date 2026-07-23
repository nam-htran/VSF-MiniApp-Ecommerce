import { apiRequest } from './client';

/**
 * Address helpers served by our backend (see server/app/geo):
 *  - the Vietnam administrative-unit picker, fetched one level at a time
 *    so the app never ships the whole ~600 KB tree;
 *  - reverse geocoding, which the app cannot do itself — it runs on the
 *    server, which is allowed to call a third-party geocoder.
 */
export type AdminUnit = { code: string; name: string };

export const listProvinces = () => apiRequest<AdminUnit[]>('/geo/provinces');

export const listDistricts = (provinceCode: string) =>
  apiRequest<AdminUnit[]>(
    `/geo/districts?province=${encodeURIComponent(provinceCode)}`
  );

export const listWards = (districtCode: string) =>
  apiRequest<AdminUnit[]>(
    `/geo/wards?district=${encodeURIComponent(districtCode)}`
  );

/** null address = the provider was unreachable; keep the coordinates. */
export const reverseGeocode = (lat: number, lng: number) =>
  apiRequest<{ address: string | null; lat: number; lng: number }>(
    `/geocode/reverse?lat=${lat}&lng=${lng}`
  );
