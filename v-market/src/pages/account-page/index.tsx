import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  Avatar,
  Button,
  Icon,
  Skeleton,
  Typography,
  useDidShow,
  useNavigate,
  type IIconName,
} from '@v-miniapp/ui-react';
import { signOut, useSession } from '@/lib/auth';
import { listAddresses, type SavedAddress } from '@/api/addresses';
import { listOrders } from '@/api/orders';
import { getMyShop, type Shop } from '@/api/shops';
import { AddressBookSheet } from '@/components/address-book';
import { ShopBanner } from '@/components/shop-preview';
import {
  ORDER_STAGES,
  orderStage,
  showOrders,
  type OrderStage,
} from '@/lib/order-stage';

/**
 * Browsing never required an account — login lives here and at checkout,
 * not at the door. Signed out is a normal state, not an error.
 *
 * Signed in, the page reads top to bottom as: who you are, where your
 * orders have got to, then everything you can change. The chrome's search
 * pill is off here (see NO_SEARCH) — the red hero is this page's header.
 */
const AccountPage = () => {
  const session = useSession();
  return session ? <SignedIn /> : <Guest />;
};

const SignedIn = () => {
  const session = useSession();

  const [addresses, setAddresses] = useState<SavedAddress[]>([]);
  const [bookOpen, setBookOpen] = useState(false);

  const refresh = useCallback(async () => {
    setAddresses(await listAddresses().catch(() => []));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!session) return null;
  const { user } = session;

  return (
    <div className="flex flex-col gap-4 bg-alias-layer-01 pb-8">
      <Hero
        name={user.name}
        role={user.role}
        phone={user.phone}
        onClick={() => setBookOpen(true)}
      />

      <OrderStages />

      <Group title="Mua sắm">
        <Row
          icon="stack-x-plus"
          label="Giỏ hàng"
          to="/cart"
          animation="none"
        />
      </Group>

      <Group title="Công cụ">
        <SellerShopBanner />
        {/* Only operators see this, and the page checks the role again —
            hiding a menu row is presentation, not access control. */}
        {user.role === 'ADMIN' && (
          <>
            <Divider />
            <Row
              icon="discount-code"
              label="Đối soát thanh toán"
              hint="Tiền chờ hoàn"
              to="/ops"
            />
          </>
        )}
      </Group>

      <Group title="Khác">
        <Row
          icon="arrow-door-out"
          label="Đăng xuất"
          danger
          onClick={signOut}
        />
      </Group>

      {/* Management mode: no onSelect, so the list only edits — add, set
          default, delete — with nothing to pick. */}
      <AddressBookSheet
        open={bookOpen}
        onClose={() => setBookOpen(false)}
        addresses={addresses}
        defaultRecipientName={user.name ?? ''}
        defaultPhone={user.phone ?? ''}
        onChanged={() => void refresh()}
        onCreated={() => void refresh()}
      />
    </div>
  );
};

/**
 * Who you are, in one quiet row — the cards below carry the page, so this
 * only has to identify the account. The safe area is padded here because
 * this page has no navigation bar of its own.
 */
const Hero = ({
  name,
  role,
  phone,
  onClick,
}: {
  name: string | null;
  role: string;
  phone: string | null;
  onClick: () => void;
}) => (
  <div
    className="px-3"
    style={{ paddingTop: 'calc(var(--safe-area-inset-top, 44px) + 16px)' }}>
    <button
      type="button"
      aria-label="Mở cài đặt tài khoản"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-2xl bg-alias-background p-3 text-left shadow-sm active:bg-alias-layer-01">
      <Avatar size={48} shape="circle" label={(name ?? '?').charAt(0)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Typography size="large" weight="bold" className="truncate">
          {name ?? 'Người dùng V-App'}
        </Typography>
        <Typography size="small" color="text-tertiary" className="truncate">
          {[role === 'SELLER' ? 'Người bán' : 'Người mua', phone]
            .filter(Boolean)
            .join(' · ')}
        </Typography>
      </div>
      <Icon
        name="chevron-right"
        size={18}
        color="text-tertiary"
        className="shrink-0"
      />
    </button>
  </div>
);

const SellerShopBanner = () => {
  const navigate = useNavigate();
  const [shop, setShop] = useState<Shop | null | undefined>(undefined);

  useEffect(() => {
    getMyShop()
      .then(setShop)
      .catch(() => setShop(null));
  }, []);

  if (shop === undefined) return <Skeleton className="h-36 w-full" />;

  return (
    <ShopBanner
      shop={shop}
      fallbackName="Mở cửa hàng của bạn"
      emptyText="Bắt đầu bán hàng trên V-Market"
      actionLabel={shop ? 'Quản lý' : 'Mở shop'}
      onClick={() => navigate('/seller')}
    />
  );
};

/**
 * "Đơn mua" — the four stages an order passes through, each a way into the
 * orders list already filtered. The badge counts what the first page of
 * orders holds; orders come back newest first, so anything still moving is
 * on it, and the page never waits for the number to arrive.
 */
const OrderStages = () => {
  const [counts, setCounts] = useState<Partial<Record<OrderStage, number>>>({});
  const navigate = useNavigate();

  const tally = useCallback(() => {
    let alive = true;
    listOrders()
      .then(page => {
        if (!alive) return;
        const counted: Partial<Record<OrderStage, number>> = {};
        for (const order of page.items) {
          const stage = orderStage(order);
          counted[stage] = (counted[stage] ?? 0) + 1;
        }
        setCounts(counted);
      })
      // No badges then. They decorate the tiles; the tiles still work.
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  useEffect(tally, [tally]);

  // Same as the orders list: kept alive, so without this the badges keep
  // counting the orders as they stood the first time the page opened.
  useDidShow(tally);

  const open = (stage: OrderStage | 'all') => {
    showOrders(stage);
    navigate('/orders', { animation: { type: 'none' } });
  };

  return (
    <section className="mx-3 flex flex-col rounded-2xl bg-alias-background py-3 shadow-sm">
      <button
        type="button"
        onClick={() => open('all')}
        className="flex items-center justify-between px-4 pb-3 active:opacity-60">
        <Typography size="base" weight="bold">
          Đơn mua
        </Typography>
        <span className="flex items-center gap-0.5">
          <Typography size="x-small" color="text-secondary">
            Xem lịch sử mua hàng
          </Typography>
          <Icon name="chevron-right" size={14} color="text-tertiary" />
        </span>
      </button>

      <div className="grid grid-cols-4">
        {ORDER_STAGES.map(({ stage, label, icon }) => (
          <button
            key={stage}
            type="button"
            onClick={() => open(stage)}
            className="flex flex-col items-center gap-1.5 px-1 active:opacity-60">
            <span className="relative">
              <Icon name={icon} size={26} className="text-brand" />
              {!!counts[stage] && (
                <span className="absolute -right-2.5 -top-1.5 min-w-4 rounded-full bg-global-red-red-60 px-1 text-center">
                  <Typography
                    size="2x-small"
                    weight="bold"
                    className="text-global-basic-white">
                    {counts[stage]}
                  </Typography>
                </span>
              )}
            </span>
            <Typography
              size="2x-small"
              color="text-secondary"
              className="text-center leading-tight">
              {label}
            </Typography>
          </button>
        ))}
      </div>
    </section>
  );
};

const Group = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="mx-3 flex flex-col gap-1.5">
    <Typography
      size="x-small"
      weight="semibold"
      color="text-secondary"
      className="px-1">
      {title}
    </Typography>
    <div className="flex flex-col overflow-hidden rounded-2xl bg-alias-background shadow-sm">
      {children}
    </div>
  </section>
);

const Row = ({
  icon,
  label,
  hint,
  danger,
  to,
  animation,
  onClick,
}: {
  icon: IIconName;
  label: string;
  hint?: string;
  /** Destructive: paints the row red, as the mock's "Log out" does. */
  danger?: boolean;
  /** Where the row goes. Rows that open a sheet pass onClick instead. */
  to?: string;
  animation?: 'none';
  onClick?: () => void;
}) => {
  const navigate = useNavigate();
  const tone = danger ? 'text-global-red-red-60' : undefined;
  return (
    <button
      type="button"
      onClick={
        onClick ??
        (() =>
          to &&
          navigate(to, animation ? { animation: { type: animation } } : {}))
      }
      className="flex items-center gap-3 px-4 py-3.5 text-left active:bg-alias-layer-01">
      <Icon
        name={icon}
        size={20}
        color={danger ? undefined : 'text-secondary'}
        className={`shrink-0 ${tone ?? ''}`}
      />
      <Typography size="small" weight="semibold" className={`flex-1 ${tone ?? ''}`}>
        {label}
      </Typography>
      {hint && (
        <Typography size="x-small" color="text-tertiary">
          {hint}
        </Typography>
      )}
    </button>
  );
};

const Divider = () => (
  <div className="mx-4 border-b border-alias-border-subtle-01" />
);

const Guest = () => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
      <Avatar size={64} shape="circle" label="?" />
      <Typography size="large" weight="semibold">
        Bạn đang xem với tư cách khách
      </Typography>
      <Typography size="small" color="text-secondary">
        Duyệt cửa hàng và thêm giỏ thoải mái — đăng nhập chỉ cần khi đặt
        hàng.
      </Typography>
      <Button shape="pill" type="solid" theme="brand" onClick={() => navigate('/login')}>
        Đăng nhập với V-App
      </Button>
    </div>
  );
};

export default AccountPage;
