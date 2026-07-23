import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Icon,
  Image,
  Skeleton,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import {
  advanceShopOrder,
  listShopOrders,
  type SellerShopOrder,
  type ShopOrderView,
} from '@/api/orders';
import { SHOP_STATUS, StatusChip, formatDate } from '@/components/order-bits';
import { formatVnd } from '@/lib/format';

/**
 * The owner's fulfilment queue for their shop — the other half of model B,
 * where each shop drives its own delivery. Only PAID orders appear (nothing
 * to ship before payment); a filter narrows to one status, and each slice
 * has a single button walking it one step forward.
 */
type Filter = 'ALL' | ShopOrderView['status'];

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'ALL', label: 'Tất cả' },
  { key: 'CONFIRMED', label: 'Chờ giao' },
  { key: 'SHIPPING', label: 'Đang giao' },
  { key: 'DELIVERED', label: 'Đã giao' },
];

// The one forward step offered per status, or null at the end of the line.
const NEXT: Partial<
  Record<ShopOrderView['status'], { to: 'SHIPPING' | 'DELIVERED'; label: string }>
> = {
  CONFIRMED: { to: 'SHIPPING', label: 'Bắt đầu giao' },
  SHIPPING: { to: 'DELIVERED', label: 'Đã giao xong' },
};

export const SellerOrders = () => {
  const [filter, setFilter] = useState<Filter>('ALL');
  const [orders, setOrders] = useState<SellerShopOrder[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    setOrders(null);
    listShopOrders(filter === 'ALL' ? undefined : filter)
      .then(page => setOrders(page.items))
      .catch(() => setOrders([]));
  }, [filter]);

  useEffect(load, [load]);

  const advance = async (order: SellerShopOrder) => {
    const step = NEXT[order.status];
    if (!step || busy) return;
    setBusy(order.id);
    try {
      const updated = await advanceShopOrder(order.id, step.to);
      setOrders(prev =>
        prev
          ? prev
              // Drop it from a filtered list it no longer belongs to;
              // otherwise swap in the new status in place.
              .map(o => (o.id === updated.id ? updated : o))
              .filter(o => filter === 'ALL' || o.status === filter)
          : prev
      );
      Toast.show({
        type: 'positive',
        message:
          step.to === 'SHIPPING' ? 'Đã chuyển sang đang giao' : 'Đã giao xong',
        position: 'bottom',
      });
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không cập nhật được',
        position: 'bottom',
      });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="-mx-1 flex gap-2 overflow-x-auto px-4 pb-1">
        {FILTERS.map(f => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={`shrink-0 rounded-full px-3 py-1.5 ${
              filter === f.key ? 'bg-brand' : 'bg-alias-layer-01'
            }`}>
            <Typography
              size="small"
              weight={filter === f.key ? 'semibold' : 'regular'}
              className={filter === f.key ? 'text-alias-background' : undefined}
              color={filter === f.key ? undefined : 'text-secondary'}>
              {f.label}
            </Typography>
          </button>
        ))}
      </div>

      {orders === null ? (
        <div className="flex flex-col gap-2 px-3">
          <Skeleton className="h-32 w-full rounded-2xl" />
          <Skeleton className="h-32 w-full rounded-2xl" />
        </div>
      ) : orders.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-8 text-center">
          <span className="text-4xl">📭</span>
          <Typography size="small" color="text-secondary">
            Chưa có đơn nào ở mục này.
          </Typography>
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-3">
          {orders.map(order => (
            <OrderCard
              key={order.id}
              order={order}
              busy={busy === order.id}
              onAdvance={() => advance(order)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const OrderCard = ({
  order,
  busy,
  onAdvance,
}: {
  order: SellerShopOrder;
  busy: boolean;
  onAdvance: () => void;
}) => {
  const step = NEXT[order.status];
  const total = order.subtotal + order.shippingFee;
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl bg-alias-background p-3 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <Typography size="2x-small" color="text-tertiary">
          #{order.id.slice(0, 8)} · {formatDate(order.createdAt)}
        </Typography>
        <StatusChip label={SHOP_STATUS[order.status]} status={order.status} />
      </div>

      <div className="flex items-start gap-1.5">
        <Icon name="pin" size={14} className="mt-0.5 shrink-0 text-global-teal-teal-60" />
        <Typography size="x-small" color="text-secondary">
          {order.address}
        </Typography>
      </div>

      <div className="flex flex-col gap-2 border-t border-alias-border-subtle-01 pt-2">
        {order.items.map(item => (
          <div key={item.productId} className="flex gap-2.5">
            <Image
              src={item.imageUrl ?? undefined}
              alt={item.name}
              fit="cover"
              className="size-12 shrink-0 rounded-lg"
              fallback={
                <div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-global-neutral-neutral-10 text-xl">
                  🛒
                </div>
              }
            />
            <div className="flex min-w-0 flex-1 flex-col justify-center">
              <Typography size="small" className="line-clamp-1">
                {item.name}
              </Typography>
              <Typography size="2x-small" color="text-secondary">
                {formatVnd(item.price)} × {item.qty}
              </Typography>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-alias-border-subtle-01 pt-2">
        <Typography size="2x-small" color="text-tertiary">
          Tổng (gồm {formatVnd(order.shippingFee)} phí giao)
        </Typography>
        <Typography size="small" weight="bold" className="text-brand">
          {formatVnd(total)}
        </Typography>
      </div>

      {step && (
        <Button
          shape="pill"
          type="solid"
          theme="brand"
          block
          size="medium"
          loading={busy}
          onClick={onAdvance}>
          {step.label}
        </Button>
      )}
    </div>
  );
};
