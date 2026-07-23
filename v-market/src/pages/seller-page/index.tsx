import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Icon,
  Skeleton,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { getMyShop } from '@/api/shops';
import { ShopForm } from '@/components/shop-form';
import { ApiError } from '@/api/client';

/**
 * The seller channel entry. A seller's shop *is* the shop page, so this
 * only handles the one thing that page can't: opening a shop when there
 * isn't one yet. Once there is, it hands straight over to /shop, where the
 * owner edits and manages in place.
 */
type State = 'loading' | 'noshop' | 'failed';

const SellerPage = () => {
  const navigate = useNavigate();
  const [state, setState] = useState<State>('loading');

  const load = useCallback(() => {
    setState('loading');
    getMyShop()
      .then(shop =>
        navigate('/shop', { params: { id: shop.id }, replace: true })
      )
      .catch(error => {
        // 403 = logged in but no shop yet: show the open-shop form.
        setState(
          error instanceof ApiError && error.status === 403 ? 'noshop' : 'failed'
        );
      });
  }, [navigate]);

  useEffect(load, [load]);

  if (state === 'loading') {
    return (
      <div className="pt-chrome flex flex-col gap-3 px-4">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
      </div>
    );
  }

  if (state === 'failed') {
    return (
      <div className="pt-chrome px-3">
        <Alert
          type="negative"
          title="Không tải được kênh người bán"
          message="Thử lại nhé."
          action={<Button shape="pill" onClick={load}>Thử lại</Button>}
        />
      </div>
    );
  }

  return (
    <div className="pt-chrome flex flex-col gap-4 px-4 pb-8">
      <div className="flex flex-col items-center gap-2 pt-4 text-center">
        <Icon name="office" size={44} className="text-brand" />
        <Typography size="large" weight="bold">
          Mở cửa hàng của bạn
        </Typography>
        <Typography size="small" color="text-secondary">
          Bắt đầu bán hàng trên V-Market. Mở cửa hàng là xong — bạn thành người
          bán ngay.
        </Typography>
      </div>
      {/* After opening, reload: getMyShop now succeeds and hands over to the
          shop page. */}
      <ShopForm onSaved={load} />
    </div>
  );
};

export default SellerPage;
