import { IAppConfig } from '@v-miniapp/ui-react';
import { AddressPicker } from './components/address-picker';
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
  pages: [
    {
      pathname: '/',
      Component: HomePage,
      navigationBar: {
        title: <AddressPicker />,
      },
      bottomTabBarId: 'home',
    },
    {
      pathname: '/orders',
      Component: OrdersPage,
      navigationBar: { title: 'Đơn hàng' },
      bottomTabBarId: 'orders',
    },
    {
      pathname: '/account',
      Component: AccountPage,
      navigationBar: { title: 'Tài khoản' },
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
