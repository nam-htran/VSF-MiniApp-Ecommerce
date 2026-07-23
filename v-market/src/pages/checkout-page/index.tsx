import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Button,
  Icon,
  Image,
  Skeleton,
  Toast,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  cartSubtotal,
  clearCart,
  lineKey,
  linePrice,
  setQty,
  useCart,
  type CartLine,
} from '@/lib/cart';
import { useSession } from '@/lib/auth';
import {
  placeOrder,
  quoteOrder,
  SHIPPING_FEE_PER_SHOP,
  type OrderQuote,
  type QuotedShop,
  type VoucherChoice,
} from '@/api/orders';
import { VoucherSheet } from '@/components/voucher-picker';
import { listAddresses, type SavedAddress } from '@/api/addresses';
import { initPayment } from '@/api/payments';
import { AddressBookSheet } from '@/components/address-book';
import { PaymentSheet } from '@/components/payment-sheet';
import { ApiError } from '@/api/client';
import { formatVnd } from '@/lib/format';
import { estimateDelivery } from '@/lib/delivery';

/**
 * The checkout screen, Shopee-shaped: a delivery address picked from the
 * buyer's address book, the cart grouped by shop with a shipping fee per
 * shop, one payment method, then the price breakdown and a place-order bar.
 *
 * Behind the session guard, so a session always exists here. The client
 * sends product ids and quantities only; the server prices, stock-checks
 * and totals the order under a lock, and its total is the real one — the
 * breakdown here is a faithful preview, not the source of truth.
 */

/** Group cart lines by shop so each shop shows as its own block, and the
 *  shipping fee counts once per shop — matching the server's split. Uses
 *  shopId when known, falling back to the name for demo items added from
 *  the detail page (which don't carry a shop id). */
type ShopGroup = {
  key: string;
  shopId?: string;
  shopName: string;
  lines: CartLine[];
};

const groupByShop = (lines: CartLine[]): ShopGroup[] => {
  const groups = new Map<string, ShopGroup>();
  for (const line of lines) {
    const key = line.product.shopId ?? line.product.shopName ?? '—';
    const existing = groups.get(key);
    if (existing) existing.lines.push(line);
    else
      groups.set(key, {
        key,
        shopId: line.product.shopId,
        shopName: line.product.shopName ?? 'Cửa hàng',
        lines: [line],
      });
  }
  return [...groups.values()];
};

const CheckoutPage = () => {
  const navigate = useNavigate();
  const session = useSession();
  const { lines } = useCart();

  // null = still loading the address book.
  const [addresses, setAddresses] = useState<SavedAddress[] | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [bookOpen, setBookOpen] = useState(false);
  const [placing, setPlacing] = useState(false);
  // Set once the order is placed and a payment session opened — drives the
  // payment sheet. The order already exists (PENDING) at this point.
  const [payment, setPayment] = useState<{
    paymentId: string;
    amount: number;
  } | null>(null);

  const refresh = useCallback(async () => {
    const list = await listAddresses().catch(() => []);
    setAddresses(list);
    // Keep the current pick if it still exists; otherwise fall to the
    // default, then the newest.
    setSelectedId(prev =>
      prev && list.some(a => a.id === prev)
        ? prev
        : (list.find(a => a.isDefault) ?? list[0])?.id
    );
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const groups = useMemo(() => groupByShop(lines), [lines]);

  // The server prices the basket — same grouping and the same voucher
  // arithmetic the order will use — so this preview cannot quote one figure
  // and charge another. Until it answers, fall back to the plain sum, which
  // is only ever an over-estimate (no voucher applied yet), never under.
  const [quote, setQuote] = useState<OrderQuote | null>(null);
  // shopId -> code the buyer picked. Empty means "best applies itself".
  const [picked, setPicked] = useState<VoucherChoice>({});
  useEffect(() => {
    if (lines.length === 0) return;
    let current = true;
    quoteOrder(
      lines.map(line => ({
        productId: line.product.id,
        variantId: line.variant?.id,
        qty: line.qty,
      })),
      picked
    )
      .then(result => {
        if (current) setQuote(result);
      })
      .catch(() => {
        if (current) setQuote(null);
      });
    return () => {
      current = false;
    };
  }, [lines, picked]);

  const merchandise = quote?.merchandise ?? cartSubtotal(lines);
  const shipping = quote?.shipping ?? groups.length * SHIPPING_FEE_PER_SHOP;
  const discount = quote?.discount ?? 0;
  const total = quote?.total ?? merchandise + shipping;
  // What the flash-sale markdown already took off, separate from vouchers:
  // `merchandise` is the sum at sale prices, so this is shown struck through
  // on that line rather than as a second deduction.
  const markdown = lines.reduce(
    (sum, { product, qty }) =>
      sum +
      (product.oldPrice && product.oldPrice > product.price
        ? (product.oldPrice - product.price) * qty
        : 0),
    0
  );

  const selected = addresses?.find(a => a.id === selectedId) ?? null;
  // One free-text address field on the server: fold recipient, phone and
  // the saved location line into it.
  const composed = selected
    ? `${selected.recipientName} · ${selected.phone}\n${selected.addressLine}`
    : null;
  const canPlace = composed !== null && !placing;

  // An empty cart means "nothing to check out" only before an order exists.
  // Placing one clears the cart on purpose, so without the two guards below
  // the page would swap to the empty state at the very moment the payment
  // sheet should open — the order is placed, but the buyer is shown an
  // empty basket and never gets to pay.
  if (lines.length === 0 && !placing && !payment) return <EmptyCheckout />;

  const place = async () => {
    if (!composed || placing) return;
    setPlacing(true);

    let order;
    try {
      order = await placeOrder(
        composed,
        lines.map(line => ({
          productId: line.product.id,
          variantId: line.variant?.id,
          qty: line.qty,
        })),
        // The server re-validates each pick and silently falls back to the
        // best voucher, so a stale choice can never fail the order.
        picked
      );
    } catch (error) {
      const detail =
        error instanceof ApiError &&
        error.body &&
        typeof error.body === 'object' &&
        'detail' in error.body
          ? String((error.body as { detail: unknown }).detail)
          : 'Không đặt được đơn, thử lại nhé';
      Toast.show({ type: 'negative', message: detail, position: 'bottom' });
      setPlacing(false);
      return;
    }

    // The items are an order now — the cart's job is done whether or not
    // payment goes through (an unpaid order stays reachable from /orders).
    clearCart();
    try {
      const session = await initPayment(order.id, Math.round(order.total));
      setPayment({ paymentId: session.paymentId, amount: order.total });
    } catch {
      Toast.show({
        type: 'informative',
        message: 'Đã tạo đơn — mở phần Đơn hàng để thanh toán',
        position: 'bottom',
      });
      navigate('/orders');
    } finally {
      setPlacing(false);
    }
  };

  return (
    <div
      className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01"
      style={{
        // Room for the fixed place-order bar.
        paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 76px)',
      }}>
      <div className="px-4 pb-1">
        <Typography size="2x-large" weight="bold" component="h1">
          Thanh toán
        </Typography>
      </div>

      <AddressPicker
        selected={selected}
        loading={addresses === null}
        onOpen={() => setBookOpen(true)}
      />

      {groups.map(group => (
        <ShopGroupCard
          key={group.key}
          group={group}
          buyerAddress={selected?.addressLine}
          quoted={quote?.shops.find(s => s.shopId === group.shopId) ?? null}
          onPickVoucher={code =>
            setPicked(prev => {
              const next = { ...prev };
              if (code === null) delete next[group.shopId!];
              else next[group.shopId!] = code;
              return next;
            })
          }
        />
      ))}

      <PaymentCard />

      <BreakdownCard
        merchandise={merchandise}
        shipping={shipping}
        markdown={markdown}
        discount={discount}
        total={total}
      />

      <PlaceOrderBar
        total={total}
        disabled={!canPlace}
        loading={placing}
        onPlace={place}
      />

      <AddressBookSheet
        open={bookOpen}
        onClose={() => setBookOpen(false)}
        addresses={addresses ?? []}
        selectedId={selectedId}
        defaultRecipientName={session?.user.name ?? ''}
        defaultPhone={session?.user.phone ?? ''}
        onSelect={setSelectedId}
        onChanged={() => void refresh()}
        onCreated={created => {
          void refresh();
          setSelectedId(created.id);
        }}
      />

      {payment && (
        <PaymentSheet
          paymentId={payment.paymentId}
          amount={payment.amount}
          // Paid or abandoned, the order now lives in the orders list.
          onClose={() => navigate('/orders')}
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

const AddressPicker = ({
  selected,
  loading,
  onOpen,
}: {
  selected: SavedAddress | null;
  loading: boolean;
  onOpen: () => void;
}) => (
  <Card>
    <span className="flex items-center gap-2">
      <Icon name="pin" size={18} className="text-brand" />
      <Typography size="base" weight="bold">
        Địa chỉ nhận hàng
      </Typography>
    </span>

    {loading ? (
      <Skeleton className="h-12 w-full rounded-lg" />
    ) : selected ? (
      <button
        type="button"
        onClick={onOpen}
        className="flex items-start gap-2 text-left">
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="flex flex-wrap items-center gap-x-2">
            <Typography size="small" weight="semibold">
              {selected.recipientName}
            </Typography>
            <Typography size="x-small" color="text-secondary">
              {selected.phone}
            </Typography>
          </span>
          <Typography size="x-small" color="text-secondary" className="line-clamp-2 break-words">
            {selected.addressLine}
          </Typography>
        </div>
        <span className="flex shrink-0 items-center pt-0.5">
          <Typography size="x-small" className="text-brand">
            Thay đổi
          </Typography>
          <Icon name="chevron-right" size={16} color="text-tertiary" />
        </span>
      </button>
    ) : (
      <button
        type="button"
        onClick={onOpen}
        className="flex items-center gap-2 rounded-xl border border-dashed border-alias-border-subtle-01 px-3 py-3 text-left">
        <Icon name="plus" size={18} className="shrink-0 text-brand" />
        <Typography size="small" color="text-secondary" className="flex-1">
          Thêm địa chỉ nhận hàng
        </Typography>
        <Icon name="chevron-right" size={16} color="text-tertiary" />
      </button>
    )}
  </Card>
);

/** Compact +/- stepper; the totals above recompute live as it changes.
 *  Minimum is 1 here — removing an item is done back in the cart, not at
 *  checkout, so a stray tap can't empty the order mid-payment. */
const QtyStepper = ({ lineId, qty }: { lineId: string; qty: number }) => (
  <div className="flex items-center gap-2 rounded-full bg-alias-layer-01 px-1.5 py-0.5">
    <button
      type="button"
      aria-label="Giảm số lượng"
      disabled={qty <= 1}
      onClick={() => setQty(lineId, Math.max(1, qty - 1))}
      className="flex size-6 items-center justify-center rounded-full active:bg-alias-background disabled:opacity-30">
      <Icon name="minus" size={12} />
    </button>
    <Typography size="small" weight="bold" className="min-w-4 text-center tabular-nums">
      {qty}
    </Typography>
    <button
      type="button"
      aria-label="Tăng số lượng"
      onClick={() => setQty(lineId, qty + 1)}
      className="flex size-6 items-center justify-center rounded-full active:bg-alias-background">
      <Icon name="plus" size={12} />
    </button>
  </div>
);

const ShopGroupCard = ({
  group,
  buyerAddress,
  quoted,
  onPickVoucher,
}: {
  group: ShopGroup;
  buyerAddress?: string;
  /** This shop's slice of the server's quote — vouchers included. */
  quoted: QuotedShop | null;
  onPickVoucher: (code: string | null) => void;
}) => {
  const navigate = useNavigate();
  const [voucherOpen, setVoucherOpen] = useState(false);
  // Each shop ships from its own province, so the estimate is per card —
  // the buyer's address sharpens it when the two are in the same region.
  const eta = estimateDelivery(
    group.lines[0]?.product.shopProvince ?? null,
    buyerAddress
  );
  return (
  <Card>
    {group.shopId ? (
      <button
        type="button"
        onClick={() => navigate('/shop', { params: { id: group.shopId! } })}
        className="flex items-center gap-1.5 text-left">
        <Icon name="office" size={15} className="shrink-0 text-global-teal-teal-60" />
        <Typography size="small" weight="semibold" className="truncate">
          {group.shopName}
        </Typography>
        <Icon name="chevron-right" size={12} color="text-tertiary" />
      </button>
    ) : (
      <span className="flex items-center gap-1.5">
        <Icon name="office" size={15} className="shrink-0 text-global-teal-teal-60" />
        <Typography size="small" weight="semibold" className="truncate">
          {group.shopName}
        </Typography>
      </span>
    )}

    {group.lines.map(line => (
      <div key={lineKey(line)} className="flex gap-3">
        <Image
          src={line.variant?.imageUrl ?? line.product.image}
          alt={line.product.name}
          fit="cover"
          className="size-14 shrink-0 rounded-lg"
          fallback={
            <div
              className={`flex size-14 shrink-0 items-center justify-center rounded-lg text-2xl ${line.product.tint}`}>
              {line.product.emoji}
            </div>
          }
        />
        <div className="flex min-w-0 flex-1 flex-col justify-center">
          <Typography size="small" className="line-clamp-2">
            {line.product.name}
          </Typography>
          {/* Which option is being bought — the buyer is about to pay, so
              the size had better be on screen. */}
          {line.variant && (
            <Typography size="2x-small" color="text-secondary">
              {line.variant.label}
            </Typography>
          )}
          <div className="flex items-center justify-between">
            <Typography size="small" weight="semibold">
              {formatVnd(linePrice(line))}
            </Typography>
            <QtyStepper lineId={lineKey(line)} qty={line.qty} />
          </div>
        </div>
      </div>
    ))}

    {/* This shop's vouchers. Shown whenever the shop has any, so the buyer
        can see what they'd need for the ones that don't apply yet. */}
    {quoted && quoted.vouchers.length > 0 && (
      <button
        type="button"
        onClick={() => setVoucherOpen(true)}
        className="flex items-center gap-2 rounded-xl bg-alias-layer-01 px-2.5 py-2 text-left">
        <Icon name="discount-code" size={16} className="shrink-0 text-brand" />
        <div className="flex min-w-0 flex-1 flex-col">
          {quoted.voucherCode ? (
            <>
              <Typography size="x-small" weight="semibold" className="truncate text-brand">
                {quoted.voucherCode}
              </Typography>
              <Typography size="2x-small" className="text-global-green-green-70">
                Giảm {formatVnd(quoted.discount)}
              </Typography>
            </>
          ) : (
            <Typography size="x-small" color="text-secondary">
              Chọn mã giảm giá ({quoted.vouchers.length})
            </Typography>
          )}
        </div>
        <Icon name="chevron-right" size={14} color="text-tertiary" />
      </button>
    )}

    <VoucherSheet
      open={voucherOpen}
      offers={quoted?.vouchers ?? []}
      selected={quoted?.voucherCode ?? null}
      onPick={code => {
        onPickVoucher(code);
        setVoucherOpen(false);
      }}
      onClose={() => setVoucherOpen(false)}
    />

    <div className="flex flex-col gap-1.5 border-t border-alias-border-subtle-01 pt-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Icon name="clock" size={14} className="text-global-teal-teal-60" />
          <Typography size="x-small" color="text-secondary">
            Dự kiến giao
          </Typography>
        </span>
        <Typography size="small" weight="semibold">
          {eta.days}
          {eta.sameRegion && (
            <Typography size="2x-small" color="text-tertiary">
              {' '}
              · cùng khu vực
            </Typography>
          )}
        </Typography>
      </div>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Icon name="scooter-front" size={14} className="text-global-teal-teal-60" />
          <Typography size="x-small" color="text-secondary">
            Phí vận chuyển
          </Typography>
        </span>
        <Typography size="small">{formatVnd(SHIPPING_FEE_PER_SHOP)}</Typography>
      </div>
    </div>
  </Card>
  );
};

const PaymentCard = () => (
  <Card>
    <span className="flex items-center gap-2">
      <Icon name="wallet" size={18} className="text-brand" />
      <Typography size="base" weight="bold">
        Phương thức thanh toán
      </Typography>
    </span>

    {/* One method only. Selected and fixed — the real payment flow
        (V-App initPayment + IPN) is the next milestone; for now the order
        is created in PENDING and this stands in for the wallet screen. */}
    <span className="flex items-center gap-2 rounded-xl bg-alias-layer-01 px-3 py-2.5">
      <Icon name="circle-check" type="fill" size={20} className="text-brand" />
      <div className="flex flex-1 flex-col">
        <Typography size="small" weight="semibold">
          Ví V-App
        </Typography>
        <Typography size="2x-small" color="text-tertiary">
          Giả lập — thanh toán thật sẽ bổ sung sau
        </Typography>
      </div>
    </span>
  </Card>
);

const BreakdownCard = ({
  merchandise,
  shipping,
  markdown,
  discount,
  total,
}: {
  merchandise: number;
  shipping: number;
  /** Flash-sale markdown already inside `merchandise` — shown struck
   *  through on that line, not deducted a second time. */
  markdown: number;
  /** Voucher saving across every shop, genuinely subtracted from the total.
   *  Deliberately unlabelled with a code: a basket spanning two shops can
   *  carry two vouchers, and naming one of them beside their combined
   *  amount would misstate both. Each shop's card names its own. */
  discount: number;
  total: number;
}) => (
  <Card>
    <Row
      label="Tổng tiền hàng"
      value={formatVnd(merchandise)}
      was={markdown > 0 ? formatVnd(merchandise + markdown) : undefined}
    />
    <Row label="Tổng phí vận chuyển" value={formatVnd(shipping)} />
    {discount > 0 && (
      <Row label="Mã giảm giá" value={formatVnd(discount)} tone="save" />
    )}
    <div className="flex items-center justify-between border-t border-alias-border-subtle-01 pt-2">
      <Typography size="base" weight="bold">
        Tổng thanh toán
      </Typography>
      <Typography size="large" weight="bold" className="text-brand">
        {formatVnd(total)}
      </Typography>
    </div>
  </Card>
);

const Row = ({
  label,
  value,
  was,
  tone,
}: {
  label: string;
  value: string;
  /** Original price, struck through before the current one. */
  was?: string;
  tone?: 'save';
}) => (
  <div className="flex items-center justify-between gap-3">
    <Typography
      size="small"
      color={tone === 'save' ? undefined : 'text-secondary'}
      className={tone === 'save' ? 'text-global-green-green-70' : undefined}>
      {label}
    </Typography>
    <span className="flex shrink-0 items-baseline gap-1.5">
      {was && (
        <Typography size="x-small" color="text-tertiary" className="line-through">
          {was}
        </Typography>
      )}
      <Typography
        size="small"
        weight={tone === 'save' ? 'semibold' : 'regular'}
        className={tone === 'save' ? 'text-global-green-green-70' : undefined}>
        {tone === 'save' ? `−${value}` : value}
      </Typography>
    </span>
  </div>
);

const PlaceOrderBar = ({
  total,
  disabled,
  loading,
  onPlace,
}: {
  total: number;
  disabled: boolean;
  loading: boolean;
  onPlace: () => void;
}) => (
  // One full-width action carrying its own amount, rather than a total
  // beside a small button — the breakdown card above already itemises it,
  // so the figure appeared twice on one bar.
  <div
    className="fixed inset-x-0 bottom-0 z-40 border-t border-alias-border-subtle-01 bg-alias-background px-4 pt-2"
    style={{ paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 8px)' }}>
    <Button
      shape="pill"
      type="solid"
      theme="brand"
      size="large"
      block
      loading={loading}
      disabled={disabled}
      onClick={onPlace}>
      <span className="flex w-full items-center justify-between gap-3">
        <span>Đặt hàng</span>
        <span className="tabular-nums">{formatVnd(total)}</span>
      </span>
    </Button>
  </div>
);

const EmptyCheckout = () => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
      <span className="text-5xl">🛒</span>
      <Typography size="large" weight="semibold">
        Giỏ hàng đang trống
      </Typography>
      <Typography size="small" color="text-secondary">
        Thêm sản phẩm vào giỏ trước khi thanh toán.
      </Typography>
      <Button shape="pill" type="outline" onClick={() => navigate('/')}>
        Xem sản phẩm
      </Button>
    </div>
  );
};

export default CheckoutPage;
