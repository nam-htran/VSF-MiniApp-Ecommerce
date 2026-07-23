import { useEffect, useState, type ReactNode } from 'react';
import {
  Button,
  Icon,
  Image,
  Skeleton,
  Toast,
  Typography,
  useLocation,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  getProduct,
  listProducts,
  listShopProducts,
  type ApiProduct,
  type ApiProductDetail,
} from '@/api/products';
import { listAddresses } from '@/api/addresses';
import { ProductStrip } from '@/components/product-strip';
import { ReviewsSection, Stars } from '@/components/reviews-section';
import { addToCart } from '@/lib/cart';
import { estimateDelivery } from '@/lib/delivery';
import { formatVnd } from '@/lib/format';
import type { ProductCardData } from '@/lib/product-card';

/** API product → the compact card the suggestion strips render. */
const suggestionCard = (
  p: ApiProduct & { shopName?: string }
): ProductCardData => ({
  id: p.id,
  name: p.name,
  price: p.price,
  oldPrice: p.originalPrice ?? undefined,
  image: p.imageUrl ?? undefined,
  unit: p.unit ?? undefined,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
  shopId: p.shopId,
  shopName: p.shopName,
});

/**
 * Product detail at /product?id=… (single-level path, id in the query).
 * Rendered under the platform navigation bar — the app's floating chrome is
 * suppressed here (see TopChromeLayout NO_CHROME).
 *
 * The card that was tapped arrives in navigation state for an instant first
 * paint; the full detail — shop origin, contact, real stock — is always
 * fetched so the shipping and estimate sections can fill in.
 */
type View = {
  id: string;
  name: string;
  price: number;
  oldPrice?: number;
  image?: string;
  images?: string[];
  unit?: string;
  description?: string;
  emoji: string;
  tint: string;
  stock?: number;
  shopId?: string;
  shopName?: string;
  shopAddress?: string | null;
  shopProvince?: string | null;
  shopPhone?: string | null;
  ratingAverage?: number;
  ratingCount?: number;
};

const fromDetail = (p: ApiProductDetail): View => ({
  id: p.id,
  name: p.name,
  price: p.price,
  oldPrice: p.originalPrice ?? undefined,
  image: p.imageUrl ?? undefined,
  images: p.imageUrls?.length ? p.imageUrls : p.imageUrl ? [p.imageUrl] : [],
  unit: p.unit ?? undefined,
  description: p.description,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
  stock: p.stock,
  shopId: p.shopId,
  shopName: p.shopName ?? undefined,
  shopAddress: p.shopAddress,
  shopProvince: p.shopProvince,
  shopPhone: p.shopPhone,
  ratingAverage: p.ratingAverage,
  ratingCount: p.ratingCount,
});

const ProductPage = () => {
  const location = useLocation();
  const passed = (location?.state as { product?: ProductCardData } | undefined)
    ?.product;
  const id = location?.params?.id ?? passed?.id;

  const [detail, setDetail] = useState<ApiProductDetail | null>(null);
  const [missing, setMissing] = useState(false);
  // The buyer's default address, if any — lets the estimate say "same area".
  const [buyerAddress, setBuyerAddress] = useState<string | undefined>();

  useEffect(() => {
    if (!id) {
      setMissing(true);
      return;
    }
    getProduct(id)
      .then(setDetail)
      .catch(() => {
        if (!passed) setMissing(true);
      });
    listAddresses()
      .then(list => {
        const chosen = list.find(a => a.isDefault) ?? list[0];
        setBuyerAddress(chosen?.addressLine);
      })
      .catch(() => setBuyerAddress(undefined));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (missing) return <NotFound />;

  const view: View | null = detail
    ? fromDetail(detail)
    : passed
      ? {
          ...passed,
          shopId: passed.shopId,
          shopName: passed.shopName,
          images: passed.image ? [passed.image] : [],
        }
      : null;

  if (!view) return <DetailSkeleton />;
  return <Detail view={view} buyerAddress={buyerAddress} />;
};

const Detail = ({
  view,
  buyerAddress,
}: {
  view: View;
  buyerAddress?: string;
}) => {
  const eta = estimateDelivery(view.shopProvince ?? null, buyerAddress);

  const [sameShop, setSameShop] = useState<ProductCardData[]>([]);
  const [similar, setSimilar] = useState<ProductCardData[]>([]);

  useEffect(() => {
    if (view.shopId) {
      listShopProducts(view.shopId, 12)
        .then(page =>
          setSameShop(
            page.items.filter(p => p.id !== view.id).map(suggestionCard)
          )
        )
        .catch(() => setSameShop([]));
    }
    listProducts(16)
      .then(page =>
        setSimilar(
          page.items
            .filter(p => p.id !== view.id && p.shopId !== view.shopId)
            .slice(0, 10)
            .map(suggestionCard)
        )
      )
      .catch(() => setSimilar([]));
  }, [view.id, view.shopId]);

  return (
    <div
      className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01"
      style={{
        paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 72px)',
      }}>
      <div className="bg-alias-background">
        <ImageCarousel
          images={view.images ?? []}
          emoji={view.emoji}
          tint={view.tint}
          alt={view.name}
        />
      </div>

      <Card>
        <div className="flex flex-wrap items-baseline gap-x-2">
          <Typography
            size="2x-large"
            weight="bold"
            className={view.oldPrice ? 'text-global-red-red-60' : undefined}>
            {formatVnd(view.price)}
          </Typography>
          {view.oldPrice && (
            <Typography size="small" color="text-tertiary" className="line-through">
              {formatVnd(view.oldPrice)}
            </Typography>
          )}
        </div>
        <Typography size="large" weight="bold" component="h1">
          {view.name}
        </Typography>
        {view.ratingCount !== undefined && view.ratingCount > 0 && (
          <span className="flex items-center gap-1.5">
            <Stars value={view.ratingAverage ?? 0} />
            <Typography size="x-small" color="text-secondary">
              {(view.ratingAverage ?? 0).toFixed(1)} · {view.ratingCount} đánh giá
            </Typography>
          </span>
        )}
        {view.unit && (
          <Typography size="small" color="text-secondary">
            {view.unit}
          </Typography>
        )}
        {view.stock !== undefined && (
          <Typography
            size="x-small"
            className={
              view.stock > 0 ? 'text-global-teal-teal-60' : 'text-global-red-red-60'
            }>
            {view.stock > 0 ? `Còn ${view.stock} sản phẩm` : 'Tạm hết hàng'}
          </Typography>
        )}
      </Card>

      {/* Shipping: estimate from the shop's province, plus origin and
          contact. Only shows once the fetched detail brings the shop in. */}
      {(view.shopName || view.shopProvince) && (
        <Card>
          <InfoRow
            icon="scooter-front"
            title="Giao đến khu vực của bạn"
            value={`${eta.days}${eta.sameRegion ? ' · cùng khu vực' : ''}`}
          />
          {(view.shopAddress || view.shopProvince) && (
            <InfoRow
              icon="pin"
              title="Giao từ"
              value={
                view.shopAddress
                  ? `${view.shopAddress}${view.shopProvince ? `, ${view.shopProvince}` : ''}`
                  : (view.shopProvince ?? '')
              }
            />
          )}
          {view.shopName && (
            <InfoRow icon="office" title="Cửa hàng" value={view.shopName} />
          )}
          {view.shopPhone && (
            <InfoRow icon="phone" title="Liên hệ" value={view.shopPhone} />
          )}
        </Card>
      )}

      <Card>
        <Typography size="base" weight="bold" component="h2">
          Mô tả sản phẩm
        </Typography>
        <Typography size="small" color="text-secondary" className="whitespace-pre-line">
          {view.description ?? 'Người bán chưa bổ sung mô tả cho sản phẩm này.'}
        </Typography>
      </Card>

      <Card>
        <Typography size="base" weight="bold" component="h2">
          Chính sách &amp; điều khoản
        </Typography>
        <Policy text="Thanh toán an toàn qua cổng V-App." />
        <Policy text="Đổi trả trong 7 ngày nếu hàng lỗi do nhà sản xuất." />
        <Policy text="Thông tin nhận hàng chỉ dùng để giao đơn này." />
      </Card>

      <ReviewsSection productId={view.id} />

      {view.shopName && (
        <ProductStrip
          title={`Sản phẩm khác của ${view.shopName}`}
          products={sameShop}
        />
      )}
      <ProductStrip title="Sản phẩm tương tự" products={similar} />

      <BuyBar view={view} />
    </div>
  );
};

/** Swipeable image gallery with dots. One image shows plainly; none falls
 *  back to the emoji tile. Scroll-snap so each swipe lands on one photo. */
const ImageCarousel = ({
  images,
  emoji,
  tint,
  alt,
}: {
  images: string[];
  emoji: string;
  tint: string;
  alt: string;
}) => {
  const [active, setActive] = useState(0);

  if (images.length === 0) {
    return (
      <div className={`flex h-72 w-full items-center justify-center text-7xl ${tint}`}>
        {emoji}
      </div>
    );
  }

  return (
    <div className="relative">
      <div
        className="flex snap-x snap-mandatory overflow-x-auto"
        onScroll={event => {
          const el = event.currentTarget;
          setActive(Math.round(el.scrollLeft / el.clientWidth));
        }}>
        {images.map((url, i) => (
          <Image
            key={i}
            src={url}
            alt={alt}
            fit="cover"
            className="h-72 w-full shrink-0 snap-center"
          />
        ))}
      </div>
      {images.length > 1 && (
        <div className="absolute inset-x-0 bottom-2 flex justify-center gap-1.5">
          {images.map((_, i) => (
            <span
              key={i}
              className={`size-1.5 rounded-full ${
                i === active ? 'bg-brand' : 'bg-alias-background/70'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const Card = ({ children }: { children: ReactNode }) => (
  <div className="mx-3 flex flex-col gap-2 rounded-2xl bg-alias-background p-3.5 shadow-sm">
    {children}
  </div>
);

const InfoRow = ({
  icon,
  title,
  value,
}: {
  icon: 'scooter-front' | 'pin' | 'office' | 'phone';
  title: string;
  value: string;
}) => (
  <div className="flex items-start gap-2">
    <Icon name={icon} size={16} className="mt-0.5 shrink-0 text-global-teal-teal-60" />
    <div className="flex min-w-0 flex-1 flex-col">
      <Typography size="2x-small" color="text-tertiary">
        {title}
      </Typography>
      <Typography size="small">{value}</Typography>
    </div>
  </div>
);

const Policy = ({ text }: { text: string }) => (
  <span className="flex items-start gap-2">
    <Icon name="check" size={14} className="mt-0.5 shrink-0 text-global-teal-teal-60" />
    <Typography size="x-small" color="text-secondary">
      {text}
    </Typography>
  </span>
);

const BuyBar = ({ view }: { view: View }) => {
  const navigate = useNavigate();
  const card: ProductCardData = {
    id: view.id,
    name: view.name,
    price: view.price,
    oldPrice: view.oldPrice,
    image: view.image,
    unit: view.unit,
    description: view.description,
    emoji: view.emoji,
    tint: view.tint,
    shopId: view.shopId,
    shopName: view.shopName,
  };
  return (
    <div
      className="fixed inset-x-0 bottom-0 z-40 flex gap-2 border-t border-alias-border-subtle-01 bg-alias-background px-4 pt-2"
      style={{ paddingBottom: 'calc(var(--safe-area-inset-bottom, 0px) + 8px)' }}>
      <Button
        type="outline"
        theme="brand"
        block
        onClick={() => {
          addToCart(card);
          Toast.show({
            type: 'positive',
            message: 'Đã thêm vào giỏ hàng',
            position: 'bottom',
          });
        }}>
        Thêm vào giỏ
      </Button>
      <Button
        type="solid"
        theme="brand"
        block
        onClick={() => {
          addToCart(card);
          navigate('/cart');
        }}>
        Mua ngay
      </Button>
    </div>
  );
};

const DetailSkeleton = () => (
  <div className="pt-chrome flex flex-col gap-2 bg-alias-layer-01">
    <Skeleton className="h-72 w-full" />
    <div className="mx-3 flex flex-col gap-2 rounded-2xl bg-alias-background p-3.5">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-6 w-2/3" />
    </div>
    <Skeleton className="mx-3 h-24 rounded-2xl" />
  </div>
);

const NotFound = () => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
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
