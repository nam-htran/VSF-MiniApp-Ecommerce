import {
  Button,
  Icon,
  Image,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  cartSubtotal,
  removeLine,
  setQty,
  useCart,
  type CartLine,
} from '@/lib/cart';
import { useSession } from '@/lib/auth';
import { formatVnd } from '@/lib/format';

const CartPage = () => {
  const { lines } = useCart();
  const navigate = useNavigate();

  return (
    <div
      className="pt-chrome flex min-h-full flex-col"
      style={{
        // Room for the fixed checkout bar above the tab bar.
        paddingBottom: 'calc(var(--vsf-current-bottom-tab-bar-height, 56px) + 88px)',
      }}>
      <div className="px-4 pb-2">
        <Typography size="2x-large" weight="bold" component="h1">
          Giỏ hàng
        </Typography>
      </div>

      {lines.length === 0 ? (
        <EmptyCart />
      ) : (
        <>
          <div className="flex flex-col gap-2">
            {groupByShop(lines).map(group => (
              <div
                key={group.key}
                className="mx-4 flex flex-col gap-2 rounded-2xl bg-alias-background p-3 shadow-sm">
                {group.shopId ? (
                  <button
                    type="button"
                    onClick={() =>
                      navigate('/shop', { params: { id: group.shopId! } })
                    }
                    className="flex items-center gap-1.5 text-left">
                    <Icon name="office" size={14} className="shrink-0 text-global-teal-teal-60" />
                    <Typography size="small" weight="semibold" className="truncate">
                      {group.shopName}
                    </Typography>
                    <Icon name="chevron-right" size={12} color="text-tertiary" />
                  </button>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Icon name="office" size={14} className="shrink-0 text-global-teal-teal-60" />
                    <Typography size="small" weight="semibold" className="truncate">
                      {group.shopName}
                    </Typography>
                  </span>
                )}
                {group.lines.map((line, i) => (
                  <div
                    key={line.product.id}
                    className={i > 0 ? 'border-t border-alias-border-subtle-01 pt-2' : ''}>
                    <CartRow line={line} />
                  </div>
                ))}
              </div>
            ))}
          </div>
          <CheckoutBar lines={lines} />
        </>
      )}
    </div>
  );
};

/** Group cart lines by shop — one card per shop, like checkout. */
type CartGroup = {
  key: string;
  shopId?: string;
  shopName: string;
  lines: CartLine[];
};

const groupByShop = (lines: CartLine[]): CartGroup[] => {
  const groups = new Map<string, CartGroup>();
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

const CartRow = ({ line }: { line: CartLine }) => {
  const { product, qty } = line;
  const navigate = useNavigate();

  // The photo and the title open the product; the stepper and the bin keep
  // their own taps. Two sibling buttons rather than one wrapping the row —
  // a button inside a button is invalid, and the controls must stay live.
  const open = () =>
    navigate('/product', { params: { id: product.id }, state: { product } });

  return (
    <div className="flex gap-3">
      <button type="button" aria-label={product.name} onClick={open} className="shrink-0">
        <Image
          src={product.image}
          alt={product.name}
          fit="cover"
          className="size-20 shrink-0 rounded-lg"
          fallback={
            <div
              className={`flex size-20 shrink-0 items-center justify-center rounded-lg text-3xl ${product.tint}`}>
              {product.emoji}
            </div>
          }
        />
      </button>

      <div className="flex min-w-0 flex-1 flex-col">
        <button
          type="button"
          onClick={open}
          className="flex min-w-0 flex-col items-start text-left">
          <Typography size="small" weight="bold" className="line-clamp-1">
            {product.name}
          </Typography>
          {product.unit && (
            <Typography size="2x-small" color="text-secondary">
              {product.unit}
            </Typography>
          )}
          <Typography
            size="base"
            weight="bold"
            className={product.oldPrice ? 'text-global-red-red-60' : undefined}>
            {formatVnd(product.price)}
          </Typography>
        </button>

        <div className="mt-auto flex items-center justify-between">
          <QtyStepper id={product.id} qty={qty} />
          <button
            type="button"
            aria-label={`Xoá ${product.name} khỏi giỏ`}
            onClick={() => removeLine(product.id)}
            className="p-1">
            <Icon name="trash" size={16} color="text-tertiary" />
          </button>
        </div>
      </div>
    </div>
  );
};

const QtyStepper = ({ id, qty }: { id: string; qty: number }) => (
  <div className="flex items-center gap-3 rounded-full bg-alias-layer-01 px-2 py-1">
    {/* setQty(0) removes the line, so minus at qty 1 behaves like trash. */}
    <button
      type="button"
      aria-label="Giảm số lượng"
      onClick={() => setQty(id, qty - 1)}
      className="p-0.5">
      <Icon name="minus" size={14} />
    </button>
    <Typography size="small" weight="bold" className="min-w-4 text-center tabular-nums">
      {qty}
    </Typography>
    <button
      type="button"
      aria-label="Tăng số lượng"
      onClick={() => setQty(id, qty + 1)}
      className="p-0.5">
      <Icon name="plus" size={14} />
    </button>
  </div>
);

const CheckoutBar = ({ lines }: { lines: CartLine[] }) => {
  const navigate = useNavigate();
  const session = useSession();

  const startCheckout = () => {
    // Ask for the session at the moment of the action, not on the page:
    // browsing and filling a cart stay anonymous (review rule 3.4.8). On
    // return from /login the button is tapped again, now with a session.
    // /checkout is also guarded, so a deep link there is safe too.
    navigate(session ? '/checkout' : '/login');
  };

  return (
    <div
      className="fixed inset-x-0 z-40 flex items-center justify-between gap-3 border-t border-alias-border-subtle-01 bg-alias-background px-4 py-2"
      style={{ bottom: 'var(--vsf-current-bottom-tab-bar-height, 56px)' }}>
      <div className="flex flex-col">
        <Typography size="x-small" color="text-secondary">
          Tạm tính
        </Typography>
        <Typography size="large" weight="bold">
          {formatVnd(cartSubtotal(lines))}
        </Typography>
      </div>
      <Button type="solid" theme="brand" onClick={startCheckout}>
        Đặt hàng
      </Button>
    </div>
  );
};

const EmptyCart = () => {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center gap-3 px-8 pt-24 text-center">
      <span className="text-5xl">🛒</span>
      <Typography size="large" weight="semibold">
        Giỏ hàng đang trống
      </Typography>
      <Typography size="small" color="text-secondary">
        Ghé gian hàng và thêm vài món — không cần đăng nhập.
      </Typography>
      <Button type="outline" onClick={() => navigate('/')}>
        Xem sản phẩm
      </Button>
    </div>
  );
};

export default CartPage;
