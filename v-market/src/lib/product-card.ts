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
});
