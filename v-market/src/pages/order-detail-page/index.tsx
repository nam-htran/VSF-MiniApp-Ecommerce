import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  Button,
  Icon,
  Skeleton,
  Toast,
  Typography,
  useDidShow,
  useLocation,
  useNavigate,
} from '@v-miniapp/ui-react';
import { cancelOrder, getOrder, type OrderView } from '@/api/orders';
import { ApiError } from '@/api/client';
import { initPayment } from '@/api/payments';
import {
  ORDER_STATUS,
  ShopBlock,
  StatusChip,
  formatDate,
} from '@/components/order-bits';
import { OrderTrackingMap } from '@/components/order-tracking-map';
import { PaymentSheet } from '@/components/payment-sheet';
import { formatVnd } from '@/lib/format';

/**
 * One order at /order?id=… — the buyer's view after checkout. A paid order
 * shows the (simulated) delivery tracker; an unpaid one offers to pay
 * again. Behind the session guard, and GET /orders/{id} is owner-only, so
 * this can only ever be your own order.
 */
type State =
  | { status: 'loading' }
  | { status: 'ready'; order: OrderView }
  | { status: 'missing' };

const OrderDetailPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const id = location?.params?.id;

  const [state, setState] = useState<State>({ status: 'loading' });
  const [payment, setPayment] = useState<{
    paymentId: string;
    amount: number;
  } | null>(null);
  const [paying, setPaying] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const fetchOrder = useCallback(
    (showSkeleton: boolean) => {
      if (!id) {
        setState({ status: 'missing' });
        return;
      }
      if (showSkeleton) setState({ status: 'loading' });
      getOrder(id)
        .then(order => setState({ status: 'ready', order }))
        .catch(() => setState({ status: 'missing' }));
    },
    [id]
  );

  const load = useCallback(() => fetchOrder(true), [fetchOrder]);

  useEffect(load, [load]);

  // keepAlive keeps this page mounted, so the first load would otherwise
  // be the only one — re-read the order each time the buyer comes back,
  // quietly, since there is already an order on screen.
  useDidShow(() => fetchOrder(false));

  const order = state.status === 'ready' ? state.order : null;

  // And while the parcel is moving, keep re-reading: the demo courier
  // advances it server-side on a timer (advance_simulated_fulfilment), so
  // a buyer sitting here should watch it arrive rather than have to leave
  // the screen and come back to find out.
  const inFlight =
    order?.status === 'PAID' &&
    order.shopOrders.some(
      s => s.status === 'CONFIRMED' || s.status === 'SHIPPING'
    );

  useEffect(() => {
    if (!inFlight) return;
    const id = setInterval(() => fetchOrder(false), 15_000);
    return () => clearInterval(id);
  }, [inFlight, fetchOrder]);

  if (state.status === 'loading') return <DetailSkeleton />;
  if (order === null) return <NotFound />;

  const cancelNow = async () => {
    setCancelling(true);
    try {
      // The server answers with the order in its new state, so the screen
      // reflects what actually happened rather than what was asked for.
      const updated = await cancelOrder(order.id);
      setState({ status: 'ready', order: updated });
      Toast.show({
        type: 'positive',
        message: 'Đã huỷ đơn, hàng được trả lại kho',
        position: 'bottom',
      });
    } catch (error) {
      Toast.show({
        type: 'negative',
        message:
          error instanceof ApiError &&
          error.body &&
          typeof error.body === 'object' &&
          'detail' in error.body
            ? String((error.body as { detail: unknown }).detail)
            : 'Không huỷ được đơn',
        position: 'bottom',
      });
    } finally {
      setCancelling(false);
    }
  };

  const payNow = async () => {
    setPaying(true);
    try {
      const session = await initPayment(order.id, Math.round(order.total));
      setPayment({ paymentId: session.paymentId, amount: order.total });
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không mở được thanh toán, thử lại nhé',
        position: 'bottom',
      });
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01 pb-8">
      <div className="flex items-center justify-between px-4 pb-1">
        <div className="flex flex-col">
          <Typography size="large" weight="bold">
            Đơn #{order.id.slice(0, 8)}
          </Typography>
          <Typography size="2x-small" color="text-tertiary">
            {formatDate(order.createdAt)}
          </Typography>
        </div>
        <StatusChip label={ORDER_STATUS[order.status]} status={order.status} />
      </div>

      {order.status === 'PAID' ? (
        <Card>
          <OrderTrackingMap
            createdAt={order.createdAt}
            shopOrders={order.shopOrders}
          />
        </Card>
      ) : order.status === 'PENDING' ? (
        <Card>
          <span className="flex items-center gap-2">
            <Icon name="clock" size={18} className="text-global-amber-amber-60" />
            <Typography size="small" weight="semibold">
              Đơn chưa thanh toán
            </Typography>
          </span>
          <Typography size="x-small" color="text-secondary">
            Hoàn tất thanh toán để cửa hàng bắt đầu chuẩn bị và giao hàng.
          </Typography>
          <Button
            shape="pill"
            type="solid"
            theme="brand"
            block
            loading={paying}
            onClick={payNow}>
            Thanh toán {formatVnd(order.total)}
          </Button>
          {/* Cancelling is the buyer's own decision, so it is offered
              plainly rather than hidden — but as the quiet option, since
              paying is what they came here to do. The server decides
              whether it is still allowed; a shop that has started shipping
              refuses, and the message says so. */}
          <Button
            shape="pill"
            type="ghost"
            block
            loading={cancelling}
            onClick={cancelNow}>
            Huỷ đơn
          </Button>
        </Card>
      ) : null}

      <Card>
        <span className="flex items-center gap-2">
          <Icon name="pin" size={16} className="shrink-0 text-brand" />
          <Typography size="small" weight="semibold">
            Địa chỉ nhận hàng
          </Typography>
        </span>
        <Typography size="x-small" color="text-secondary" className="whitespace-pre-line">
          {order.address}
        </Typography>
      </Card>

      <div className="mx-3 flex flex-col gap-3 rounded-2xl bg-alias-background p-3 shadow-sm">
        {order.shopOrders.map(shopOrder => (
          <ShopBlock
            key={shopOrder.id}
            shopOrder={shopOrder}
            onShopClick={shopId => navigate('/shop', { params: { id: shopId } })}
          />
        ))}
        <div className="flex items-center justify-between border-t border-alias-border-subtle-01 pt-2">
          <Typography size="small" color="text-secondary">
            Tổng cộng
          </Typography>
          <Typography size="large" weight="bold" className="text-brand">
            {formatVnd(order.total)}
          </Typography>
        </div>
      </div>

      {payment && (
        <PaymentSheet
          paymentId={payment.paymentId}
          amount={payment.amount}
          onClose={result => {
            setPayment(null);
            // Paid: reload so the tracker replaces the pay prompt. Cancelled:
            // the order stays PENDING, nothing to refetch.
            if (result === 'paid') load();
          }}
        />
      )}
    </div>
  );
};

const Card = ({ children }: { children: ReactNode }) => (
  <div className="mx-3 flex flex-col gap-3 rounded-2xl bg-alias-background p-3.5 shadow-sm">
    {children}
  </div>
);

const DetailSkeleton = () => (
  <div className="pt-chrome flex flex-col gap-2 bg-alias-layer-01 px-3 pb-8">
    <Skeleton className="h-8 w-40" />
    <Skeleton className="h-48 w-full rounded-2xl" />
    <Skeleton className="h-24 w-full rounded-2xl" />
  </div>
);

const NotFound = () => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
      <Icon name="circle-question" size={48} color="text-tertiary" />
      <Typography size="large" weight="semibold">
        Không tìm thấy đơn hàng
      </Typography>
      <Typography size="small" color="text-secondary">
        Đơn có thể không tồn tại hoặc không thuộc về bạn.
      </Typography>
      <Button shape="pill" type="outline" onClick={() => navigate('/orders')}>
        Về danh sách đơn
      </Button>
    </div>
  );
};

export default OrderDetailPage;
