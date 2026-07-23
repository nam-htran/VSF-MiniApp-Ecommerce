import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

/**
 * Sale vouchers, straight from the database — no simulated copy anywhere.
 * A voucher lives between two timestamps; the server only ever returns the
 * ones running right now, so an expired sale leaves the promo strip on its
 * own, with nothing to clean up.
 *
 * Nobody types a code: the best applicable voucher is already applied to
 * the price a card shows and to the order the server charges.
 */
export type Voucher = {
  id: string;
  code: string;
  description: string;
  /** null = the whole marketplace; otherwise this shop's items only. */
  shopId: string | null;
  /** null = anything in scope; otherwise only this product category. It is
   *  also what min_order is measured against. */
  category: string | null;
  discountType: 'PERCENT' | 'AMOUNT';
  discountValue: number;
  /** Caps a percentage voucher; null for a flat amount. */
  maxDiscount: number | null;
  minOrder: number;
  startsAt: string;
  endsAt: string;
  status: 'ACTIVE' | 'DISABLED';
};

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

/** Public — what is running now. The promo strip needs no session. */
export function listVouchers(shopId?: string) {
  const query = shopId ? `?shopId=${encodeURIComponent(shopId)}` : '';
  return apiRequest<{ items: Voucher[] }>(`/vouchers${query}`);
}

/** The seller's own, expired ones included, so they can manage the list. */
export function listMyVouchers() {
  return apiRequest<{ items: Voucher[] }>('/vouchers/mine', {
    headers: bearer(),
  });
}

export type NewVoucher = {
  code: string;
  description: string;
  /** null = everything the shop sells. */
  category?: string | null;
  discountType: 'PERCENT' | 'AMOUNT';
  discountValue: number;
  maxDiscount?: number | null;
  minOrder?: number;
  startsAt: string;
  endsAt: string;
};

export function createVoucher(body: NewVoucher) {
  return apiRequest<Voucher>('/vouchers', {
    method: 'POST',
    data: body,
    headers: bearer(),
  });
}

export function setVoucherStatus(id: string, status: 'ACTIVE' | 'DISABLED') {
  return apiRequest<Voucher>(`/vouchers/${id}/status`, {
    method: 'PATCH',
    data: { status },
    headers: bearer(),
  });
}
