import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

/**
 * Payment, through the mock gateway that stands in for V-App's own. On a
 * real device this is `apisAsync.initPayment` opening the native payment
 * sheet; here the MiniApp opens a session on the mock and confirms it,
 * which makes the mock send the signed IPN to our server. The order only
 * becomes PAID once that server-to-server notification lands — never from
 * the client saying so. Same seam as auth: the mock lives on its own base.
 */
const VAPP = import.meta.env.VITE_VAPP_BASE ?? 'http://127.0.0.1:4001';

// Confirming and abandoning still talk to the mock directly: on a real
// device those are the native payment sheet, not calls this app makes.
const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

type Envelope<T> = { code: number; message: string; data: T };

async function unwrap<T>(promise: Promise<Envelope<T>>): Promise<T> {
  const envelope = await promise;
  if (envelope.code !== 0) throw new Error(envelope.message);
  return envelope.data;
}

/**
 * Open the payment through our own server, not straight at the gateway.
 *
 * The MiniApp used to call the gateway directly, which left the server
 * unable to tell an abandoned basket from a buyer entering an OTP — and its
 * stock-hold sweep would cancel the second, taking the money while handing
 * the goods to someone else. Going via the server records the session on
 * the order, so the hold is extended instead.
 */
export function initPayment(orderId: string, _amount: number) {
  return apiRequest<{ paymentId: string; amount: number }>(
    '/payments/session',
    {
      method: 'POST',
      data: { orderId },
      headers: bearer(),
    }
  );
}

export function confirmPayment(paymentId: string) {
  return unwrap<{ status: string; ipnDelivered: boolean }>(
    apiRequest(`${VAPP}/simulator/payment/${paymentId}/confirm`, {
      method: 'POST',
    })
  );
}

export function abandonPayment(paymentId: string) {
  return unwrap<{ status: string }>(
    apiRequest(`${VAPP}/simulator/payment/${paymentId}/abandon`, {
      method: 'POST',
    })
  );
}


/**
 * Money the marketplace received but could not apply to an order. Operator
 * only — it carries gateway payment ids and amounts across every shop.
 */
export type PaymentExceptionView = {
  id: string;
  /** What a refund is issued against; still meaningful once our own order
   *  has been cancelled. */
  gatewayPaymentId: string;
  orderId: string | null;
  amount: number;
  reason: string;
  status: 'OPEN' | 'RESOLVED';
  createdAt: string;
};

export function listPaymentExceptions() {
  return apiRequest<{ items: PaymentExceptionView[] }>('/payments/exceptions', {
    headers: bearer(),
  });
}

/** Record that a refund was issued. Moves no money — see the ops screen. */
export function resolvePaymentException(id: string) {
  return apiRequest<{ id: string; status: string }>(
    `/payments/exceptions/${id}/resolve`,
    { method: 'POST', headers: bearer() }
  );
}
