import { IAppConfig } from '@v-miniapp/ui-react';
import HomePage from './pages/home-page';
import AboutPage from './pages/about-page';
import ProductsPage from './pages/products-page';

export const getAppConfig = (): IAppConfig => ({
  pages: [
    {
      pathname: '/',
      Component: HomePage,
      navigationBar: {
        title: 'V-MiniApp Home',
      },
      bottomTabBarId: 'home',
    },
    {
      pathname: '/about',
      Component: AboutPage,
      navigationBar: {
        title: 'V-MiniApp About',
      },
      bottomTabBarId: 'about',
    },

    {
      pathname: '/products',
      Component: ProductsPage,
      navigationBar: {
        title: 'Products',
        backIcon: true,
      },
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
      {
        id: 'home',
        name: 'Home',
        path: '/',
        icon: {
          name: 'house',
        },
      },
      {
        id: 'about',
        name: 'About',
        path: '/about',
        icon: {
          name: 'circle-info',
        },
      },
    ],
  },
});
