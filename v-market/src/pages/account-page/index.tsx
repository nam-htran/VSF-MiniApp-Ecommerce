import {
  Avatar,
  Button,
  Icon,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { signOut, useSession } from '@/lib/auth';

/**
 * Browsing never required an account — login lives here and at checkout,
 * not at the door. Signed out is a normal state, not an error.
 */
const AccountPage = () => {
  const session = useSession();
  return session ? <SignedIn /> : <Guest />;
};

const SignedIn = () => {
  const session = useSession();
  if (!session) return null;
  const { user } = session;

  return (
    <div
      className="pt-chrome flex flex-col gap-4 px-4">
      <div className="flex items-center gap-3 rounded-xl bg-alias-background p-4 shadow-sm">
        <Avatar size={56} shape="circle" label={(user.name ?? '?').charAt(0)} />
        <div className="flex min-w-0 flex-col">
          <Typography size="large" weight="bold" className="truncate">
            {user.name ?? 'Người dùng V-App'}
          </Typography>
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
        </div>
      </div>

      <Button type="outline" theme="neutral" onClick={signOut}>
        Đăng xuất
      </Button>
    </div>
  );
};

const Guest = () => {
  const navigate = useNavigate();
  return (
    <div
      className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
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
