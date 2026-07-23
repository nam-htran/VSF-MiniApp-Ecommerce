import { apiRequest } from './client';

/**
 * Payment, through the mock gateway that stands in for V-App's own. On a
 * real device this is `apisAsync.initPayment` opening the native payment
 * sheet; here the MiniApp opens a session on the mock and confirms it,
 * which makes the mock send the signed IPN to our server. The order only
 * becomes PAID once that server-to-server notification lands — never from
 * the client saying so. Same seam as auth: the mock lives on its own base.
 */
const VAPP = import.meta.env.VITE_VAPP_BASE ?? 'http://127.0.0.1:4001';

type Envelope<T> = { code: number; message: string; data: T };

async function unwrap<T>(promise: Promise<Envelope<T>>): Promise<T> {
  const envelope = await promise;
  if (envelope.code !== 0) throw new Error(envelope.message);
  return envelope.data;
}

export function initPayment(orderId: string, amount: number) {
  return unwrap<{ paymentId: string; amount: number }>(
    apiRequest(`${VAPP}/simulator/payment/init`, {
      method: 'POST',
      data: { orderId, amount },
    })
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
