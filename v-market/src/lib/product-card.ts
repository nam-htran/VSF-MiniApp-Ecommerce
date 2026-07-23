/**
 * What a product card on the home screen knows — and therefore what it
 * can hand to the detail page through navigation state, so the detail
 * renders instantly without refetching what the card already showed.
 *
 * Optional fields exist only on demo data so far; they become real when
 * orders and inventory can back them.
 */
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
  shopId?: string;
  shopName?: string;
  shopProvince?: string | null;
  ratingAverage?: number;
  ratingCount?: number;
  description?: string;
};
