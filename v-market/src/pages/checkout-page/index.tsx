import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Button,
  Icon,
  Image,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  Skeleton,
  Toast,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  cartSubtotal,
  clearCart,
  setQty,
  useCart,
  type CartLine,
} from '@/lib/cart';
import { useSession } from '@/lib/auth';
import { placeOrder, SHIPPING_FEE_PER_SHOP } from '@/api/orders';
import { listAddresses, type SavedAddress } from '@/api/addresses';
import { abandonPayment, confirmPayment, initPayment } from '@/api/payments';
import { AddressBookSheet } from '@/components/address-book';
import { ApiError } from '@/api/client';
import { formatVnd } from '@/lib/format';

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
type ShopGroup = { key: string; shopName: string; lines: CartLine[] };

const groupByShop = (lines: CartLine[]): ShopGroup[] => {
  const groups = new Map<string, ShopGroup>();
  for (const line of lines) {
    const key = line.product.shopId ?? line.product.shopName ?? '—';
    const existing = groups.get(key);
    if (existing) existing.lines.push(line);
    else
      groups.set(key, {
        key,
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
  const merchandise = cartSubtotal(lines);
  const shipping = groups.length * SHIPPING_FEE_PER_SHOP;
  const total = merchandise + shipping;

  const selected = addresses?.find(a => a.id === selectedId) ?? null;
  // One free-text address field on the server: fold recipient, phone and
  // the saved location line into it.
  const composed = selected
    ? `${selected.recipientName} · ${selected.phone}\n${selected.addressLine}`
    : null;
  const canPlace = composed !== null && !placing;

  if (lines.length === 0) return <EmptyCheckout />;

  const place = async () => {
    if (!composed || placing) return;
    setPlacing(true);

    let order;
    try {
      order = await placeOrder(
        composed,
        lines.map(line => ({ productId: line.product.id, qty: line.qty }))
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
        <ShopGroupCard key={group.key} group={group} />
      ))}

      <PaymentCard />

      <BreakdownCard
        merchandise={merchandise}
        shipping={shipping}
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
        <PaymentSheet paymentId={payment.paymentId} amount={payment.amount} />
      )}
    </div>
  );
};

/**
 * The V-App payment sheet, simulated. On a real device initPayment opens
 * the platform's own; here it's this. Confirming asks the gateway to
 * charge, which sends the IPN that flips the order to PAID — the client
 * never marks its own order paid. Both actions land on the orders screen.
 */
const PaymentSheet = ({
  paymentId,
  amount,
}: {
  paymentId: string;
  amount: number;
}) => {
  const navigate = useNavigate();
  const [busy, setBusy] = useState<'pay' | 'cancel' | null>(null);

  const pay = async () => {
    setBusy('pay');
    try {
      await confirmPayment(paymentId);
      Toast.show({
        type: 'positive',
        message: 'Thanh toán thành công',
        position: 'bottom',
      });
      navigate('/orders');
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Thanh toán chưa xong, thử lại nhé',
        position: 'bottom',
      });
      setBusy(null);
    }
  };

  const cancel = async () => {
    setBusy('cancel');
    try {
      await abandonPayment(paymentId);
    } catch {
      /* the order stays PENDING regardless */
    }
    Toast.show({
      type: 'informative',
      message: 'Đã huỷ thanh toán — đơn đang chờ trong Đơn hàng',
      position: 'bottom',
    });
    navigate('/orders');
  };

  return (
    <Sheet open onBackdropClick={busy ? undefined : cancel}>
      <SheetHeader title="Cổng thanh toán V-App" />
      <SheetBody>
        <div className="flex flex-col items-center gap-2 py-2 text-center">
          <Icon name="wallet" size={32} className="text-brand" />
          <Typography size="small" color="text-secondary">
            Số tiền thanh toán
          </Typography>
          <Typography size="2x-large" weight="bold" className="text-brand">
            {formatVnd(amount)}
          </Typography>
          <Typography size="2x-small" color="text-tertiary">
            Cổng thanh toán V-App (giả lập). Trên máy thật đây là màn hình
            thanh toán của nền tảng.
          </Typography>
        </div>
      </SheetBody>
      <SheetFooter>
        <div className="flex w-full gap-2">
          <Button
            type="outline"
            theme="neutral"
            block
            loading={busy === 'cancel'}
            onClick={cancel}>
            Huỷ
          </Button>
          <Button
            type="solid"
            theme="brand"
            block
            loading={busy === 'pay'}
            onClick={pay}>
            Thanh toán
          </Button>
        </div>
      </SheetFooter>
    </Sheet>
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
        className="flex items-center gap-2 text-left">
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="flex items-center gap-2">
            <Typography size="small" weight="semibold">
              {selected.recipientName}
            </Typography>
            <Typography size="x-small" color="text-secondary">
              {selected.phone}
            </Typography>
          </span>
          <Typography size="x-small" color="text-secondary" className="whitespace-pre-line">
            {selected.addressLine}
          </Typography>
        </div>
        <span className="flex shrink-0 items-center">
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
const QtyStepper = ({ id, qty }: { id: string; qty: number }) => (
  <div className="flex items-center gap-2 rounded-full bg-alias-layer-01 px-1.5 py-0.5">
    <button
      type="button"
      aria-label="Giảm số lượng"
      disabled={qty <= 1}
      onClick={() => setQty(id, Math.max(1, qty - 1))}
      className="flex size-6 items-center justify-center rounded-full active:bg-alias-background disabled:opacity-30">
      <Icon name="minus" size={12} />
    </button>
    <Typography size="small" weight="bold" className="min-w-4 text-center tabular-nums">
      {qty}
    </Typography>
    <button
      type="button"
      aria-label="Tăng số lượng"
      onClick={() => setQty(id, qty + 1)}
      className="flex size-6 items-center justify-center rounded-full active:bg-alias-background">
      <Icon name="plus" size={12} />
    </button>
  </div>
);

const ShopGroupCard = ({ group }: { group: ShopGroup }) => (
  <Card>
    <span className="flex items-center gap-1.5">
      <Icon name="office" size={15} className="shrink-0 text-global-teal-teal-60" />
      <Typography size="small" weight="semibold" className="truncate">
        {group.shopName}
      </Typography>
    </span>

    {group.lines.map(({ product, qty }) => (
      <div key={product.id} className="flex gap-3">
        <Image
          src={product.image}
          alt={product.name}
          fit="cover"
          className="size-14 shrink-0 rounded-lg"
          fallback={
            <div
              className={`flex size-14 shrink-0 items-center justify-center rounded-lg text-2xl ${product.tint}`}>
              {product.emoji}
            </div>
          }
        />
        <div className="flex min-w-0 flex-1 flex-col justify-center">
          <Typography size="small" className="line-clamp-2">
            {product.name}
          </Typography>
          <div className="flex items-center justify-between">
            <Typography size="small" weight="semibold">
              {formatVnd(product.price)}
            </Typography>
            <QtyStepper id={product.id} qty={qty} />
          </div>
        </div>
      </div>
    ))}

    <div className="flex items-center justify-between border-t border-alias-border-subtle-01 pt-2">
      <span className="flex items-center gap-1.5">
        <Icon name="scooter-front" size={14} className="text-global-teal-teal-60" />
        <Typography size="x-small" color="text-secondary">
          Phí vận chuyển
        </Typography>
      </span>
      <Typography size="small">{formatVnd(SHIPPING_FEE_PER_SHOP)}</Typography>
    </div>
  </Card>
);

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
  total,
}: {
  merchandise: number;
  shipping: number;
  total: number;
}) => (
  <Card>
    <Row label="Tổng tiền hàng" value={formatVnd(merchandise)} />
    <Row label="Tổng phí vận chuyển" value={formatVnd(shipping)} />
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

const Row = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-center justify-between">
    <Typography size="small" color="text-secondary">
      {label}
    </Typography>
    <Typography size="small">{value}</Typography>
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
  <div
    className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between gap-3 border-t border-alias-border-subtle-01 bg-alias-background px-4 pt-2"
    style={{ paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 8px)' }}>
    <div className="flex flex-col">
      <Typography size="x-small" color="text-secondary">
        Tổng thanh toán
      </Typography>
      <Typography size="large" weight="bold" className="text-brand">
        {formatVnd(total)}
      </Typography>
    </div>
    <Button
      type="solid"
      theme="brand"
      loading={loading}
      disabled={disabled}
      onClick={onPlace}>
      Đặt hàng
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
      <Button type="outline" onClick={() => navigate('/')}>
        Xem sản phẩm
      </Button>
    </div>
  );
};

export default CheckoutPage;
