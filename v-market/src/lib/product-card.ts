/**
 * What a product card on the home screen knows — and therefore what it
 * can hand to the detail page through navigation state, so the detail
 * renders instantly without refetching what the card already showed.
 *
 * Optional fields exist only on demo data so far; they become real when
 * orders and inventory can back them.
 */
import type { ApiProductListItem } from '@/api/products';

export type ProductCardData = {
  id: string;
  name: string;
  unit?: string;
  price: number;
  oldPrice?: number;
  image?: string;
  emoji: string;
  tint: string;
  shipDays?: string;
  warehouse?: string;
  sold?: number;
  category?: string | null;
  shopId?: string;
  shopName?: string;
  shopProvince?: string | null;
  ratingAverage?: number;
  ratingCount?: number;
  description?: string;
  /** `price` after the best live voucher — server-computed, and the figure
   *  the order will actually charge. Absent on demo cards. */
  effectivePrice?: number;
  /** The voucher behind that price, for the badge on the card. */
  voucher?: { code: string; description: string; discount: number } | null;
};

/**
 * How much is off this product, as a whole percent — the "-24%" badge.
 *
 * Measured from the pre-markdown price down to what the buyer actually
 * pays, so a flash-sale markdown and a voucher count together rather than
 * one of them quietly going unadvertised. 0 when nothing is off.
 */
export const discountPercent = (product: ProductCardData): number => {
  const base = product.oldPrice ?? product.price;
  const now = product.effectivePrice ?? product.price;
  if (base <= 0 || now >= base) return 0;
  return Math.round((1 - now / base) * 100);
};

/**
 * API list item → card. Every strip and grid in the app renders the same
 * card, so they all map the same way; this is that mapping, in one place.
 * The emoji/tint pair is the fallback tile shown when a photo fails.
 */
export const listItemToCard = (p: ApiProductListItem): ProductCardData => ({
  id: p.id,
  name: p.name,
  description: p.description,
  unit: p.unit ?? undefined,
  price: p.price,
  oldPrice: p.originalPrice ?? undefined,
  image: p.imageUrl ?? undefined,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
  shopId: p.shopId,
  shopName: p.shopName,
  shopProvince: p.shopProvince,
  ratingAverage: p.ratingAverage,
  ratingCount: p.ratingCount,
  sold: p.sold,
  category: p.category,
  effectivePrice: p.effectivePrice,
  voucher: p.voucher,
});
