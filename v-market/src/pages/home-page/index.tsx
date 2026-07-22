import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Image,
  PullToRefresh,
  Skeleton,
  Typography,
} from '@v-miniapp/ui-react';
import { listShops, type Shop } from '@/api/shops';

type State =
  | { status: 'loading' }
  | { status: 'ready'; shops: Shop[] }
  | { status: 'failed'; message: string };

const HomePage = () => {
  const [state, setState] = useState<State>({ status: 'loading' });

  const load = async () => {
    try {
      const page = await listShops();
      setState({ status: 'ready', shops: page.items });
    } catch (error) {
      setState({
        status: 'failed',
        message:
          error instanceof Error ? error.message : 'Không rõ nguyên nhân',
      });
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <PullToRefresh onRefresh={load}>
      <div className="flex flex-col gap-3 p-4">
        <Typography size="large" weight="bold" component="h1">
          Cửa hàng gần bạn
        </Typography>

        {state.status === 'loading' && <ShopListSkeleton />}

        {state.status === 'failed' && (
          <Alert
            type="negative"
            title="Không tải được danh sách cửa hàng"
            message={state.message}
            action={<Button onClick={load}>Thử lại</Button>}
          />
        )}

        {state.status === 'ready' &&
          (state.shops.length === 0 ? (
            <Alert
              type="informative"
              title="Chưa có cửa hàng nào"
              message="Hãy quay lại sau, hoặc tự mở một cửa hàng."
            />
          ) : (
            state.shops.map(shop => <ShopCard key={shop.id} shop={shop} />)
          ))}
      </div>
    </PullToRefresh>
  );
};

const ShopCard = ({ shop }: { shop: Shop }) => (
  <div className="overflow-hidden rounded-xl bg-alias-layer-01 shadow-sm">
    <Image
      src={shop.imageUrl ?? undefined}
      alt=""
      fit="cover"
      lazy
      className="h-36 w-full"
      // A missing image must not collapse the card and shift what follows,
      // which would also move whatever the platform measures as LCP.
      fallback={
        <div className="flex h-36 w-full items-center justify-center bg-alias-layer-02">
          <Typography size="small" color="text-tertiary">
            {shop.name}
          </Typography>
        </div>
      }
    />
    <div className="p-3">
      <Typography size="base" weight="semibold">
        {shop.name}
      </Typography>
      <Typography size="small" color="text-secondary" className="line-clamp-2">
        {shop.description}
      </Typography>
    </div>
  </div>
);

// Deliberately the same height as a real card. A skeleton larger than the
// content it stands in for can be locked in as the LCP element, because
// measurement keeps the largest element even after it leaves the DOM.
const ShopListSkeleton = () => (
  <>
    {[0, 1, 2].map(row => (
      <div key={row} className="overflow-hidden rounded-xl">
        <Skeleton className="h-36 w-full" />
        <div className="p-3">
          <Skeleton className="mb-2 h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </div>
    ))}
  </>
);

export default HomePage;
