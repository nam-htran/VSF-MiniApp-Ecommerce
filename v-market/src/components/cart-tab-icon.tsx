import { Badge, BadgeContainer } from '@v-miniapp/ui-react';
import { cartCount, useCart } from '@/lib/cart';

/**
 * The cart tab's icon, with a live count badge.
 *
 * IBottomTabBarItem has no badge field and the app config is built once
 * and never re-read — but the icon accepts a ReactNode, and a component
 * subscribes to the cart store and re-renders itself. The config object
 * stays constant; the element inside it is alive.
 *
 * Emoji because the shipped icon set has nothing for a cart or bag.
 */
export const CartTabIcon = ({ active = false }: { active?: boolean }) => {
  const { lines } = useCart();
  const count = cartCount(lines);

  return (
    <BadgeContainer>
      <span
        className={`block text-xl leading-none transition-transform ${
          // The active tab lifts and grows a touch, matching the lifted
          // filled icons on the other tabs.
          active ? '-translate-y-0.5 scale-110' : ''
        }`}>
        🛒
      </span>
      {count > 0 && <Badge>{count > 99 ? '99+' : count}</Badge>}
    </BadgeContainer>
  );
};
