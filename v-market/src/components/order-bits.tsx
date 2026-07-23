import { Icon, Image, Typography } from '@v-miniapp/ui-react';
import type { OrderView, ShopOrderView } from '@/api/orders';
import { formatVnd } from '@/lib/format';

/**
 * Shared order rendering — the status labels, the tone chip and one shop's
 * block — used by both the orders list and the order detail page. Model B
 * keeps two separate states: payment on the order, fulfilment per shop.
 */
export const ORDER_STATUS: Record<OrderView['status'], string> = {
  PENDING: 'Chờ thanh toán',
  PAID: 'Đã thanh toán',
  FAILED: 'Thanh toán lỗi',
  CANCELLED: 'Đã huỷ',
};

export const SHOP_STATUS: Record<ShopOrderView['status'], string> = {
  CONFIRMED: 'Đã xác nhận',
  SHIPPING: 'Đang giao',
  DELIVERED: 'Đã giao',
  CANCELLED: 'Đã huỷ',
};

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });

/** Fulfilment and payment states share one chip; the tone maps by name. */
export const StatusChip = ({
  label,
  status,
}: {
  label: string;
  status: string;
}) => {
  const tone =
    status === 'DELIVERED' || status === 'PAID'
      ? 'bg-global-green-green-10 text-global-green-green-70'
      : status === 'CANCELLED' || status === 'FAILED'
        ? 'bg-global-red-red-10 text-global-red-red-60'
        : 'bg-global-amber-amber-10 text-global-amber-amber-70';
  return (
    <span className={`shrink-0 rounded-full px-2 py-0.5 ${tone}`}>
      <Typography size="2x-small" weight="semibold">
        {label}
      </Typography>
    </span>
  );
};

export const ShopBlock = ({
  shopOrder,
  onShopClick,
}: {
  shopOrder: ShopOrderView;
  /** Given only where the block is not already inside a clickable card
   *  (the order detail, not the list) — makes the shop name a link. */
  onShopClick?: (shopId: string) => void;
}) => (
  <div className="flex flex-col gap-2 rounded-xl bg-alias-layer-01 p-2.5">
    <div className="flex items-center justify-between gap-2">
      {onShopClick ? (
        <button
          type="button"
          onClick={() => onShopClick(shopOrder.shopId)}
          className="flex min-w-0 items-center gap-1.5 text-left">
          <Icon name="office" size={14} className="shrink-0 text-global-teal-teal-60" />
          <Typography size="small" weight="semibold" className="truncate">
            {shopOrder.shopName}
          </Typography>
          <Icon name="chevron-right" size={12} color="text-tertiary" />
        </button>
      ) : (
        <span className="flex min-w-0 items-center gap-1.5">
          <Icon name="office" size={14} className="shrink-0 text-global-teal-teal-60" />
          <Typography size="small" weight="semibold" className="truncate">
            {shopOrder.shopName}
          </Typography>
        </span>
      )}
      <StatusChip label={SHOP_STATUS[shopOrder.status]} status={shopOrder.status} />
    </div>

    {shopOrder.items.map(item => (
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

    {shopOrder.discount > 0 && (
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1">
          <Icon
            name="discount-code"
            size={11}
            className="shrink-0 text-global-green-green-70"
          />
          <Typography size="2x-small" className="truncate text-global-green-green-70">
            {shopOrder.voucherCode ?? 'Mã giảm giá'}
          </Typography>
        </span>
        <Typography size="2x-small" weight="semibold" className="text-global-green-green-70">
          −{formatVnd(shopOrder.discount)}
        </Typography>
      </div>
    )}

    <div className="flex items-center justify-between">
      <Typography size="2x-small" color="text-tertiary">
        Phí giao hàng
      </Typography>
      <Typography size="2x-small" color="text-tertiary">
        {formatVnd(shopOrder.shippingFee)}
      </Typography>
    </div>
  </div>
);
