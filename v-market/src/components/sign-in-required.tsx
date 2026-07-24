import {
  Button,
  Icon,
  Typography,
  useNavigate,
  type IIconName,
} from '@v-miniapp/ui-react';
import type { LoginTarget } from '@/lib/routes';

/**
 * What a bottom tab shows when it needs an account: the reason, in place
 * of the tab's content, with the tab bar left alone.
 *
 * Redirecting is right for a page the user opened on purpose — they asked
 * for that page and get it back after signing in. It is wrong for a tab:
 * pressing Orders and landing on a login screen with no tab bar reads as
 * being thrown out of the app, and the other tabs go with it.
 *
 * So the tab stays put, and signing in becomes an offer rather than a
 * toll gate. Deliberately shaped like the empty states next to it — this
 * is a normal condition, not an error.
 */
export const SignInRequired = ({
  target,
  icon,
  title,
  message,
}: {
  /** Where to land after signing in — normally the tab itself. */
  target: LoginTarget;
  icon: IIconName;
  title: string;
  message: string;
}) => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
      <Icon name={icon} size={48} color="text-tertiary" />
      <Typography size="large" weight="semibold">
        {title}
      </Typography>
      <Typography size="small" color="text-secondary">
        {message}
      </Typography>
      {/* Pushed, not replaced: backing out of /login without signing in
          should come back here, not skip past the tab entirely. */}
      <Button
        shape="pill"
        type="solid"
        theme="brand"
        onClick={() => navigate('/login', { state: { loginTarget: target } })}>
        Đăng nhập với V-App
      </Button>
    </div>
  );
};
