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
          <div className="flex flex-col gap-2 px-4">
            {lines.map(line => (
              <CartRow key={line.product.id} line={line} />
            ))}
          </div>
          <CheckoutBar lines={lines} />
        </>
      )}
    </div>
  );
};

const CartRow = ({ line }: { line: CartLine }) => {
  const { product, qty } = line;
  return (
    <div className="flex gap-3 rounded-xl bg-alias-background p-2 shadow-sm">
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

      <div className="flex min-w-0 flex-1 flex-col">
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
