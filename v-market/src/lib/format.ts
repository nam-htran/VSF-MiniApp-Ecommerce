/**
 * Vietnamese number formatting: 3.000.000 ₫
 *
 * Dot for thousands and comma for decimals — the opposite of English, and
 * required by review rule 3.3.1. One place, because every price on every
 * screen goes through it.
 */
export function formatVnd(amount: number): string {
  return `${amount.toLocaleString('vi-VN')} ₫`;
}
