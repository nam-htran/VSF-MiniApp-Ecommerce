import { useEffect, useState } from 'react';
import {
  Button,
  Icon,
  Image,
  Skeleton,
  Typography,
  useLocation,
  useNavigate,
} from '@v-miniapp/ui-react';
import { getProduct } from '@/api/products';
import { formatVnd } from '@/lib/format';
import type { ProductCardData } from '@/lib/product-card';

/**
 * Product detail at /product?id=… (single-level path, id in the query).
 *
 * Two ways in:
 *  - tapped from a card: the card's data arrives in navigation state and
 *    renders instantly, no request;
 *  - opened cold (deep link): only the id exists, so the page fetches
 *    GET /products/{id} from the backend.
 * Demo cards carry made-up ids the backend has never heard of — state is
 *    what makes them work at all.
 */
const ProductPage = () => {
  const location = useLocation();
  const passed = (location?.state as { product?: ProductCardData } | undefined)
    ?.product;
  const id = location?.params?.id;

  const [state, setState] = useState<
    | { status: 'ready'; product: ProductCardData }
    | { status: 'loading' }
    | { status: 'missing' }
  >(passed ? { status: 'ready', product: passed } : { status: 'loading' });

  useEffect(() => {
    if (passed || !id) {
      if (!passed && !id) setState({ status: 'missing' });
      return;
    }
    getProduct(id)
      .then(product =>
        setState({
          status: 'ready',
          product: {
            id: product.id,
            name: product.name,
            description: product.description,
            unit: product.unit ?? undefined,
            price: product.price,
            oldPrice: product.originalPrice ?? undefined,
            image: product.imageUrl ?? undefined,
            emoji: '🛒',
            tint: 'bg-global-neutral-neutral-10',
          },
        })
      )
      .catch(() => setState({ status: 'missing' }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (state.status === 'loading') return <DetailSkeleton />;
  if (state.status === 'missing') return <NotFound />;
  return <Detail product={state.product} />;
};

const Detail = ({ product }: { product: ProductCardData }) => (
  <div
    className="flex min-h-full flex-col"
    style={{
      // Room for the fixed buy bar, plus the device's bottom inset.
      paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 72px)',
    }}>
    {/* Bleeds to the top edge; the floating back button from the app
        layout is the only chrome up there. */}
    <Image
      src={product.image}
      alt={product.name}
      fit="cover"
      className="h-72 w-full"
      fallback={
        <div
          className={`flex h-72 w-full items-center justify-center text-7xl ${product.tint}`}>
          {product.emoji}
        </div>
      }
    />

    <div className="flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-1">
        <Typography size="large" weight="bold" component="h1">
          {product.name}
        </Typography>
        {product.unit && (
          <Typography size="small" color="text-secondary">
            {product.unit}
          </Typography>
        )}
        <div className="flex flex-wrap items-baseline gap-x-2">
          <Typography
            size="2x-large"
            weight="bold"
            className={product.oldPrice ? 'text-global-red-red-60' : undefined}>
            {formatVnd(product.price)}
          </Typography>
          {product.oldPrice && (
            <Typography size="small" color="text-tertiary" className="line-through">
              {formatVnd(product.oldPrice)}
            </Typography>
          )}
        </div>
      </div>

      {(product.shipDays || product.warehouse || product.sold !== undefined) && (
        <div className="flex flex-col gap-1.5 rounded-xl bg-alias-layer-01 p-3">
          {product.shipDays && (
            <InfoRow icon="scooter-front" text={`Giao ${product.shipDays}`} />
          )}
          {product.warehouse && (
            <InfoRow icon="pin" text={`Kho ${product.warehouse}`} />
          )}
          {product.sold !== undefined && (
            <InfoRow icon="receipt" text={`Đã bán ${product.sold.toLocaleString('vi-VN')}`} />
          )}
        </div>
      )}

      <div className="flex flex-col gap-1">
        <Typography size="base" weight="bold" component="h2">
          Mô tả
        </Typography>
        <Typography size="small" color="text-secondary">
          {product.description ??
            'Người bán chưa bổ sung mô tả cho sản phẩm này.'}
        </Typography>
      </div>
    </div>

    <BuyBar />
  </div>
);

const InfoRow = ({ icon, text }: { icon: 'scooter-front' | 'pin' | 'receipt'; text: string }) => (
  <span className="flex items-center gap-2">
    <Icon name={icon} size={16} className="shrink-0 text-global-teal-teal-60" />
    <Typography size="small">{text}</Typography>
  </span>
);

/** Visual only until a cart exists. */
const BuyBar = () => (
  <div
    className="fixed inset-x-0 bottom-0 z-40 flex gap-2 border-t border-alias-border-subtle-01 bg-alias-background px-4 pt-2"
    style={{
      paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 8px)',
    }}>
    <Button type="outline" theme="brand" block>
      Thêm vào giỏ
    </Button>
    <Button type="solid" theme="brand" block>
      Mua ngay
    </Button>
  </div>
);

// Same footprint as the real content, so the skeleton cannot get locked
// in as the LCP element.
const DetailSkeleton = () => (
  <div className="flex flex-col">
    <Skeleton className="h-72 w-full" />
    <div className="flex flex-col gap-3 p-4">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-20 w-full rounded-xl" />
    </div>
  </div>
);

const NotFound = () => {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center gap-3 px-8 pt-32 text-center">
      <Icon name="circle-question" size={48} color="text-tertiary" />
      <Typography size="large" weight="semibold">
        Không tìm thấy sản phẩm
      </Typography>
      <Typography size="small" color="text-secondary">
        Sản phẩm có thể đã bị gỡ hoặc đường dẫn không đúng.
      </Typography>
      <Button type="outline" onClick={() => navigate('/')}>
        Về trang chủ
      </Button>
    </div>
  );
};

export default ProductPage;
