import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

/**
 * The buyer's saved delivery addresses — an address book kept on the
 * server, tied to the account (unlike the cart, which is device-local).
 * Every call carries the bearer token; the endpoints are owner-scoped.
 */
export type SavedAddress = {
  id: string;
  recipientName: string;
  phone: string;
  addressLine: string;
  isDefault: boolean;
  createdAt: string;
};

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

export const listAddresses = () =>
  apiRequest<SavedAddress[]>('/addresses', { headers: bearer() });

export const createAddress = (body: {
  recipientName: string;
  phone: string;
  addressLine: string;
  isDefault?: boolean;
}) =>
  apiRequest<SavedAddress>('/addresses', {
    method: 'POST',
    data: body,
    headers: bearer(),
  });

export const setDefaultAddress = (id: string) =>
  apiRequest<SavedAddress>(`/addresses/${id}/default`, {
    method: 'POST',
    headers: bearer(),
  });

export const deleteAddress = (id: string) =>
  apiRequest<void>(`/addresses/${id}`, { method: 'DELETE', headers: bearer() });
