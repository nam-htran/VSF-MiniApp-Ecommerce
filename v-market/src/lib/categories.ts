/**
 * Product categories — the chip row on the flash-sale page (and the seller
 * picker). Keys are what the backend stores on each product; labels and
 * emoji live here, on the client, so renaming one is a one-file change.
 */
export type Category = { key: string; label: string; emoji: string };

export const CATEGORIES: Category[] = [
  { key: 'dien-tu', label: 'Điện tử', emoji: '📱' },
  { key: 'am-thanh', label: 'Âm thanh', emoji: '🎧' },
  { key: 'thoi-trang', label: 'Thời trang', emoji: '👕' },
  { key: 'giay-dep', label: 'Giày dép', emoji: '👟' },
  { key: 'gia-dung', label: 'Gia dụng', emoji: '🏠' },
  { key: 'phu-kien', label: 'Phụ kiện', emoji: '🎒' },
];

export const categoryLabel = (key: string | null | undefined) =>
  CATEGORIES.find(c => c.key === key)?.label;
