import { useEffect, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Icon,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  Skeleton,
  TextField,
  Toast,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  listVappAccounts,
  loginSilently,
  loginWithConsent,
  registerVappAccount,
  type SessionResult,
  type VappAccount,
} from '@/api/auth';
import { signIn } from '@/lib/auth';

/**
 * Dev login. On the real platform this whole screen does not exist —
 * the user is already signed in to V-App and getAuthCode() is silent.
 * Here the account picker stands in for "which phone is this", and the
 * consent sheet reproduces the screen V-App itself would show.
 *
 * The two-phase flow from day 1 finally becomes visible:
 *   known user  → scope 'auth' only  → straight in, no consent
 *   new user    → CONSENT_REQUIRED   → consent sheet → 'profile phone'
 * Consent appears exactly once per account, ever. Picking a freshly
 * created account is the way to see it.
 */
type Accounts =
  | { status: 'loading' }
  | { status: 'ready'; accounts: VappAccount[] }
  | { status: 'failed'; message: string };

const LoginPage = () => {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState<Accounts>({ status: 'loading' });
  const [consentFor, setConsentFor] = useState<VappAccount | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [newName, setNewName] = useState('');

  const load = async () => {
    try {
      const list = await listVappAccounts();
      setAccounts({ status: 'ready', accounts: list });
    } catch (error) {
      setAccounts({
        status: 'failed',
        message: error instanceof Error ? error.message : String(error),
      });
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const finish = (result: SessionResult, account: VappAccount) => {
    if (result.status === 'AUTHENTICATED') {
      signIn({ token: result.token, user: result.user });
      Toast.show({
        type: 'positive',
        message: `Đã đăng nhập: ${result.user.name ?? account.name}`,
        position: 'bottom',
      });
      navigate(-1);
      return;
    }
    // New to V-Market — V-App wants the user's OK before sharing profile.
    setConsentFor(account);
  };

  const pick = async (account: VappAccount) => {
    setBusyId(account.user_id);
    try {
      finish(await loginSilently(account.user_id), account);
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không đăng nhập được, thử lại nhé',
        position: 'bottom',
      });
    } finally {
      setBusyId(null);
    }
  };

  const agreeConsent = async () => {
    if (!consentFor) return;
    const account = consentFor;
    setConsentFor(null);
    setBusyId(account.user_id);
    try {
      finish(await loginWithConsent(account.user_id), account);
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không đăng nhập được, thử lại nhé',
        position: 'bottom',
      });
    } finally {
      setBusyId(null);
    }
  };

  const register = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      const account = await registerVappAccount(name);
      setNewName('');
      await load();
      // A brand-new account always walks the consent path.
      await pick(account);
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không tạo được tài khoản',
        position: 'bottom',
      });
    }
  };

  return (
    <div
      className="pt-chrome flex min-h-full flex-col gap-4 px-4 pb-8">
      <div>
        <Typography size="2x-large" weight="bold" component="h1">
          Đăng nhập
        </Typography>
        <Typography size="small" color="text-secondary">
          Chọn tài khoản V-App của bạn. Trên điện thoại thật, bước này tự
          động — bạn đã đăng nhập V-App sẵn rồi.
        </Typography>
      </div>

      {accounts.status === 'loading' && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map(i => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      )}

      {accounts.status === 'failed' && (
        <Alert
          type="negative"
          title="Không tải được danh sách tài khoản"
          message={accounts.message}
          action={<Button shape="pill" onClick={load}>Thử lại</Button>}
        />
      )}

      {accounts.status === 'ready' && (
        <div className="flex flex-col gap-2">
          {accounts.accounts.map(account => (
            <button
              key={account.user_id}
              type="button"
              disabled={busyId !== null}
              onClick={() => pick(account)}
              className="flex items-center gap-3 rounded-xl bg-alias-background p-3 text-left shadow-sm">
              <Avatar
                src={account.avatar_url}
                size={40}
                shape="circle"
                label={account.name.charAt(0)}
              />
              <Typography size="base" weight="semibold" className="flex-1 truncate">
                {account.name}
              </Typography>
              {busyId === account.user_id ? (
                <Icon name="loader" size={18} animation="spin" />
              ) : (
                <Icon name="chevron-right" size={18} color="text-tertiary" />
              )}
            </button>
          ))}
        </div>
      )}

      <div className="mt-2 flex flex-col gap-2">
        <Typography size="small" weight="semibold" color="text-secondary">
          Chưa có tài khoản V-App?
        </Typography>
        <div className="flex gap-2">
          <TextField
            value={newName}
            onChange={setNewName}
            placeholder="Tên của bạn"
            className="flex-1"
          />
          <Button shape="pill" type="solid" theme="brand" onClick={register}>
            Tạo mới
          </Button>
        </div>
      </div>

      {/* The consent screen V-App would show — appears once per account,
          ever. Declining leaves the user browsing anonymously. */}
      <Sheet open={consentFor !== null} onBackdropClick={() => setConsentFor(null)}>
        <SheetHeader title="V-App chia sẻ thông tin" />
        <SheetBody>
          <div className="flex flex-col gap-3 pb-2">
            <Typography size="small" color="text-secondary">
              V-Market đề nghị truy cập các thông tin sau từ tài khoản V-App
              của bạn:
            </Typography>
            <div className="flex flex-col gap-2 rounded-xl bg-alias-layer-01 p-3">
              <span className="flex items-center gap-2">
                <Icon name="user" size={16} className="text-global-teal-teal-60" />
                <Typography size="small">Họ tên và ảnh đại diện</Typography>
              </span>
              <span className="flex items-center gap-2">
                <Icon name="phone" size={16} className="text-global-teal-teal-60" />
                <Typography size="small">Số điện thoại (để giao hàng)</Typography>
              </span>
            </div>
            <Typography size="x-small" color="text-tertiary">
              Màn hình này chỉ xuất hiện một lần. Lần sau bạn sẽ được đăng
              nhập tự động.
            </Typography>
          </div>
        </SheetBody>
        <SheetFooter>
          <div className="flex w-full gap-2">
            <Button
              shape="pill"
              type="outline"
              theme="neutral"
              block
              onClick={() => setConsentFor(null)}>
              Từ chối
            </Button>
            <Button shape="pill" type="solid" theme="brand" block onClick={agreeConsent}>
              Đồng ý
            </Button>
          </div>
        </SheetFooter>
      </Sheet>
    </div>
  );
};

export default LoginPage;
