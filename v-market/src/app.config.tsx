import { IAppConfig } from '@v-miniapp/ui-react';
import { BackButtonLayout } from './components/back-button-layout';
import HomePage from './pages/home-page';
import OrdersPage from './pages/orders-page';
import AccountPage from './pages/account-page';

/**
 * Routing is single-level: `/product/123` does not work, `/product?id=123`
 * does. Paths are case-sensitive, and an unregistered path silently opens
 * the home page instead of failing — so keep them lowercase and register
 * each screen here as it is built.
 *
 * See docs/day3/platform-constraints.md §3.
 */
export const getAppConfig = (): IAppConfig => ({
  // Wraps every page: one fixed back button in the same spot everywhere,
  // hidden on tab roots where there is nothing to go back to.
  Layouts: [BackButtonLayout],
  pages: [
    {
      pathname: '/',
      Component: HomePage,
      // Hidden so the promo section bleeds to the top edge. The page now
      // owns the safe area: it pads by --safe-area-inset-top itself and
      // keeps the top-right corner clear of V-App's own buttons. No back
      // button needed — this is the tab root, there is nowhere to go back.
      navigationBar: { hidden: true },
      bottomTabBarId: 'home',
    },
    {
      pathname: '/orders',
      Component: OrdersPage,
      navigationBar: { title: 'Đơn hàng', hidden: true },
      bottomTabBarId: 'orders',
    },
    {
      pathname: '/account',
      Component: AccountPage,
      navigationBar: { title: 'Tài khoản', hidden: true },
      bottomTabBarId: 'account',
    },
  ],
  animation: {
    type: 'slide_left',
  },
  pageLayout: {
    hasSpacing: false,
  },
  keepAlive: {
    enable: true,
  },
  bottomTabBar: {
    items: [
      { id: 'home', name: 'Trang chủ', path: '/', icon: { name: 'house' } },
      {
        id: 'orders',
        name: 'Đơn hàng',
        path: '/orders',
        icon: { name: 'receipt' },
      },
      {
        id: 'account',
        name: 'Tài khoản',
        path: '/account',
        icon: { name: 'user' },
      },
    ],
  },
});
