import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Icon,
  Skeleton,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { listOrders, type OrderView } from '@/api/orders';
import {
  ORDER_STATUS,
  ShopBlock,
  StatusChip,
  formatDate,
} from '@/components/order-bits';
import { formatVnd } from '@/lib/format';

/**
 * The buyer's orders — the one screen behind the session guard, so by the
 * time it renders there is always a session (see SessionGuardLayout).
 *
 * Model B shows through the layout: one order card, then a block per shop
 * inside it, each with its own fulfilment status and its own shipping fee.
 * Payment state (PENDING until the payment step exists) sits on the order;
 * fulfilment state sits on each shop.
 */
type Feed =
  | { status: 'loading' }
  | { status: 'ready'; orders: OrderView[] }
  | { status: 'failed'; message: string };

const OrdersPage = () => {
  const [feed, setFeed] = useState<Feed>({ status: 'loading' });

  const load = () => {
    setFeed({ status: 'loading' });
    // One page of 50 for now; pagination is a later concern.
    listOrders(50)
      .then(page => setFeed({ status: 'ready', orders: page.items }))
      .catch(error =>
        setFeed({
          status: 'failed',
          message: error instanceof Error ? error.message : String(error),
        })
      );
  };

  useEffect(load, []);

  if (feed.status === 'loading') return <OrdersSkeleton />;
  if (feed.status === 'failed')
    return <Failed message={feed.message} onRetry={load} />;
  if (feed.orders.length === 0) return <EmptyOrders />;

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-3 px-3 pb-6">
      <div className="px-1 pt-1">
        <Typography size="2x-large" weight="bold" component="h1">
          Đơn hàng
        </Typography>
      </div>
      {feed.orders.map(order => (
        <OrderCard key={order.id} order={order} />
      ))}
    </div>
  );
};

const OrderCard = ({ order }: { order: OrderView }) => {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate('/order', { params: { id: order.id } })}
      className="flex flex-col gap-3 rounded-2xl bg-alias-background p-3 text-left shadow-sm active:bg-alias-layer-01">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <Typography size="small" weight="bold">
            Đơn #{order.id.slice(0, 8)}
          </Typography>
          <Typography size="2x-small" color="text-tertiary">
            {formatDate(order.createdAt)}
          </Typography>
        </div>
        <StatusChip label={ORDER_STATUS[order.status]} status={order.status} />
      </div>

      <div className="flex flex-col gap-3">
        {order.shopOrders.map(shopOrder => (
          <ShopBlock key={shopOrder.id} shopOrder={shopOrder} />
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-alias-border-subtle-01 pt-2">
        <Typography size="small" color="text-secondary">
          Tổng cộng
        </Typography>
        <span className="flex items-center gap-1">
          <Typography size="large" weight="bold" className="text-brand">
            {formatVnd(order.total)}
          </Typography>
          <Icon name="chevron-right" size={16} color="text-tertiary" />
        </span>
      </div>
    </button>
  );
};

const OrdersSkeleton = () => (
  <div className="pt-chrome flex flex-col gap-3 px-3 pb-6">
    <Skeleton className="h-8 w-40" />
    {[0, 1].map(i => (
      <Skeleton key={i} className="h-40 w-full rounded-2xl" />
    ))}
  </div>
);

const Failed = ({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) => (
  <div className="pt-chrome px-3">
    <Alert
      type="negative"
      title="Không tải được đơn hàng"
      message={message}
      action={<Button onClick={onRetry}>Thử lại</Button>}
    />
  </div>
);

const EmptyOrders = () => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
      <Icon name="receipt" size={48} color="text-tertiary" />
      <Typography size="large" weight="semibold">
        Chưa có đơn hàng nào
      </Typography>
      {/* An empty state must offer a way out, not just state a fact. */}
      <Typography size="small" color="text-secondary">
        Đơn hàng của bạn sẽ hiện ở đây sau khi đặt mua.
      </Typography>
      <Button type="outline" onClick={() => navigate('/')}>
        Xem cửa hàng
      </Button>
    </div>
  );
};

export default OrdersPage;
