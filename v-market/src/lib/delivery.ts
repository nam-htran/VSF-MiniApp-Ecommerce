/**
 * A rough delivery estimate from the shop's province — no real logistics
 * feed, so this is a demo heuristic, not a promise. If the buyer's default
 * address is in the same province, it reads as same-region and fast;
 * otherwise it scales by whether the shop sits in a major hub.
 */
const MAJOR_HUBS = [
  'Hồ Chí Minh',
  'Hà Nội',
  'Đà Nẵng',
  'Hải Phòng',
  'Cần Thơ',
];

const isMajorHub = (province: string) =>
  MAJOR_HUBS.some(hub => province.includes(hub));

export type DeliveryEstimate = { days: string; sameRegion: boolean };

export function estimateDelivery(
  shopProvince: string | null,
  buyerAddress?: string | null
): DeliveryEstimate {
  if (!shopProvince) return { days: '3–5 ngày', sameRegion: false };
  if (buyerAddress && buyerAddress.includes(shopProvince)) {
    return { days: '1–2 ngày', sameRegion: true };
  }
  if (isMajorHub(shopProvince)) return { days: '2–4 ngày', sameRegion: false };
  return { days: '3–6 ngày', sameRegion: false };
}
