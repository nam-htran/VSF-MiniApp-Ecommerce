import { Avatar, Typography } from '@v-miniapp/ui-react';

/**
 * Browsing works without an account on purpose — the review rules require
 * the app to be usable by an unidentified user, so login belongs at
 * checkout rather than at the door. This screen is the placeholder until
 * that flow is wired to /auth/session.
 */
const AccountPage = () => (
  <div className="flex flex-col items-center gap-3 px-8 pt-24 text-center">
    <Avatar size={64} shape="circle" label="?" />
    <Typography size="large" weight="semibold">
      Bạn đang xem với tư cách khách
    </Typography>
    <Typography size="small" color="text-secondary">
      Có thể duyệt cửa hàng và xem sản phẩm mà không cần đăng nhập. Đăng nhập
      sẽ cần khi đặt hàng.
    </Typography>
  </div>
);

export default AccountPage;
