import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  Avatar,
  Button,
  Icon,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { signOut, useSession } from '@/lib/auth';
import { listAddresses, type SavedAddress } from '@/api/addresses';
import { AddressBookSheet } from '@/components/address-book';

/**
 * Browsing never required an account — login lives here and at checkout,
 * not at the door. Signed out is a normal state, not an error.
 *
 * Signed in, this is the hub: who you are, then the shortcuts a buyer
 * reaches for — orders, the address book, the cart.
 */
const AccountPage = () => {
  const session = useSession();
  return session ? <SignedIn /> : <Guest />;
};

const SignedIn = () => {
  const navigate = useNavigate();
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
    <div className="pt-chrome flex flex-col gap-3 bg-alias-layer-01 pb-8">
      <div className="mx-3 flex items-center gap-3 rounded-2xl bg-alias-background p-4 shadow-sm">
        <Avatar size={56} shape="circle" label={(user.name ?? '?').charAt(0)} />
        <div className="flex min-w-0 flex-col">
          <Typography size="large" weight="bold" className="truncate">
            {user.name ?? 'Người dùng V-App'}
          </Typography>
          <span className="flex items-center gap-2">
            <span className="flex items-center gap-1">
              <Icon
                name={user.role === 'SELLER' ? 'office' : 'user'}
                size={14}
                className="text-global-teal-teal-60"
              />
              <Typography size="x-small" color="text-secondary">
                {user.role === 'SELLER' ? 'Người bán' : 'Người mua'}
              </Typography>
            </span>
            {user.phone && (
              <Typography size="x-small" color="text-tertiary">
                {user.phone}
              </Typography>
            )}
          </span>
        </div>
      </div>

      <div className="mx-4 flex flex-col overflow-hidden rounded-2xl bg-alias-background shadow-sm">
        <MenuRow
          icon={<Icon name="receipt" size={20} className="shrink-0 text-brand" />}
          label="Đơn hàng của tôi"
          onClick={() => navigate('/orders', { animation: { type: 'none' } })}
        />
        <Divider />
        <MenuRow
          icon={<Icon name="pin" size={20} className="shrink-0 text-brand" />}
          label="Địa chỉ của tôi"
          hint={addresses.length ? `${addresses.length} địa chỉ` : 'Chưa có'}
          onClick={() => setBookOpen(true)}
        />
        <Divider />
        <MenuRow
          icon={<Icon name="stack-x-plus" size={20} className="shrink-0 text-brand" />}
          label="Giỏ hàng"
          onClick={() => navigate('/cart', { animation: { type: 'none' } })}
        />
        <Divider />
        <MenuRow
          icon={<Icon name="office" size={20} className="shrink-0 text-brand" />}
          label="Kênh người bán"
          hint={user.role === 'SELLER' ? 'Cửa hàng của tôi' : 'Mở cửa hàng'}
          onClick={() => navigate('/seller')}
        />
      </div>

      <div className="mx-3 mt-1">
        <Button type="outline" theme="neutral" block onClick={signOut}>
          Đăng xuất
        </Button>
      </div>

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

const MenuRow = ({
  icon,
  label,
  hint,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex items-center gap-3 px-4 py-3.5 text-left active:bg-alias-layer-01">
    {icon}
    <Typography size="small" weight="semibold" className="flex-1">
      {label}
    </Typography>
    {hint && (
      <Typography size="x-small" color="text-tertiary">
        {hint}
      </Typography>
    )}
    <Icon name="chevron-right" size={16} color="text-tertiary" />
  </button>
);

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
      <Button type="solid" theme="brand" onClick={() => navigate('/login')}>
        Đăng nhập với V-App
      </Button>
    </div>
  );
};

export default AccountPage;
