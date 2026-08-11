import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Icon,
  Image,
  Sheet,
  SheetBody,
  SheetHeader,
  Skeleton,
  Typography,
  useLocation,
  useNavigate,
} from '@v-miniapp/ui-react';
import { getShop, type Shop } from '@/api/shops';
import {
  listMyProducts,
  listShopProducts,
  type ApiProduct,
} from '@/api/products';
import { useSession } from '@/lib/auth';
import { ProductStrip } from '@/components/product-strip';
import { ProductGridSection } from '@/components/product-grid-section';
import { ProductFormSheet } from '@/components/product-form-sheet';
import { ShopForm } from '@/components/shop-form';
import { SellerOrders } from '@/components/seller-orders';
import { SellerVouchers } from '@/components/seller-vouchers';
import { Stars } from '@/components/reviews-section';
import { CATEGORIES } from '@/lib/categories';
import { formatVnd } from '@/lib/format';
import { listItemToCard, type ProductCardData } from '@/lib/product-card';

/**
 * A shop's storefront at /shop?id=… — a hero, the shop's name and stats,
 * then its products in a strip per category. Public, reached from any shop
 * name (a product, an order, the cart).
 *
 * For the owner it doubles as the manage screen: a pencil edits the shop
 * (this is also where opening a shop lands), and the product list turns
 * editable — add, edit, hide — instead of the read-only category strips.
 */
const ShopPage = () => {
  const location = useLocation();
  const session = useSession();
  const id = location?.params?.id;

  const [shop, setShop] = useState<Shop | null | undefined>(undefined);
  const [products, setProducts] = useState<ProductCardData[]>([]);
  const [mine, setMine] = useState<ApiProduct[]>([]);
  const [editingShop, setEditingShop] = useState(false);
  // The owner's view splits in two: manage the catalogue, or work the
  // fulfilment queue. Buyers never see this toggle.
  const [ownerTab, setOwnerTab] = useState<
    'products' | 'orders' | 'vouchers'
  >('products');
  // Public catalogue filter: 'all' shows a strip per category, a key shows
  // just that category as a grid.
  const [catFilter, setCatFilter] = useState<string>('all');
  // undefined = closed; null = adding; a product = editing.
  const [productForm, setProductForm] = useState<
    ApiProduct | null | undefined
  >(undefined);

  const isOwner = shop != null && session?.user.id === shop.ownerId;

  const loadShop = useCallback(() => {
    if (!id) {
      setShop(null);
      return;
    }
    getShop(id)
      .then(setShop)
      .catch(() => setShop(null));
  }, [id]);

  const loadProducts = useCallback(() => {
    if (!id) return;
    listShopProducts(id, 50)
      .then(page => setProducts(page.items.map(listItemToCard)))
      .catch(() => setProducts([]));
  }, [id]);

  useEffect(() => {
    loadShop();
    loadProducts();
  }, [loadShop, loadProducts]);

  // The owner's own products (hidden ones included) for the manage list.
  useEffect(() => {
    if (isOwner) {
      listMyProducts()
        .then(page => setMine(page.items))
        .catch(() => setMine([]));
    }
  }, [isOwner]);

  const refreshMine = () => {
    listMyProducts()
      .then(page => setMine(page.items))
      .catch(() => setMine([]));
    loadProducts();
  };

  if (shop === undefined) return <ShopSkeleton />;
  if (shop === null) return <NotFound />;

  const catSections = CATEGORIES.map(c => ({
    key: c.key,
    label: c.label,
    items: products.filter(p => p.category === c.key),
  })).filter(s => s.items.length > 0);
  const other = products.filter(
    p => !p.category || !CATEGORIES.some(c => c.key === p.category)
  );
  const sections =
    other.length > 0
      ? [...catSections, { key: '__other', label: 'Sản phẩm khác', items: other }]
      : catSections;
  const shownSections =
    catFilter === 'all' ? sections : sections.filter(s => s.key === catFilter);

  const rated = products.filter(p => (p.ratingCount ?? 0) > 0);
  const rating = rated.length
    ? rated.reduce((sum, p) => sum + (p.ratingAverage ?? 0), 0) / rated.length
    : 0;

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01 pb-8">
      {/* Banner and logo are the shop's own — a plain brand band stands in
          only until the seller uploads them. */}
      <div
        className="relative h-40 bg-brand bg-cover bg-center"
        style={shop.imageUrl ? { backgroundImage: `url("${shop.imageUrl}")` } : undefined}>
        {shop.imageUrl && <div className="absolute inset-0 bg-black/20" />}
        <span className="absolute bottom-3 left-4 flex size-16 items-center justify-center overflow-hidden rounded-2xl border-2 border-global-basic-white bg-alias-background shadow-lg">
          {shop.logoUrl ? (
            <Image src={shop.logoUrl} alt="" fit="cover" className="size-16" />
          ) : (
            <Icon name="office" size={28} className="text-brand" />
          )}
        </span>
        {isOwner && (
          <button
            type="button"
            aria-label="Sửa cửa hàng"
            onClick={() => setEditingShop(true)}
            className="absolute right-3 top-3 flex size-9 items-center justify-center rounded-full bg-alias-background/90 shadow-md backdrop-blur">
            <Icon name="pen" size={16} className="text-brand" />
          </button>
        )}
      </div>

      <div className="mx-3 -mt-1 flex flex-col gap-1.5 rounded-2xl bg-alias-background p-4 shadow-sm">
        <Typography size="2x-large" weight="bold" component="h1">
          {shop.name}
        </Typography>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {rating > 0 && (
            <span className="flex items-center gap-1">
              <Stars value={rating} />
              <Typography size="x-small" color="text-secondary">
                {rating.toFixed(1)}
              </Typography>
            </span>
          )}
          <span className="flex items-center gap-1">
            <Icon name="grid" size={13} className="text-global-teal-teal-60" />
            <Typography size="x-small" color="text-secondary">
              {products.length} sản phẩm
            </Typography>
          </span>
          {shop.province && (
            <span className="flex min-w-0 items-center gap-1">
              <Icon name="pin" size={13} className="shrink-0 text-global-teal-teal-60" />
              <Typography size="x-small" color="text-secondary" className="truncate">
                {shop.province}
              </Typography>
            </span>
          )}
        </span>
        {shop.description && (
          <Typography size="small" color="text-secondary">
            {shop.description}
          </Typography>
        )}
      </div>

      {isOwner ? (
        <>
          <div className="-mx-1 flex gap-2 px-4 pt-1">
            {(
              [
                ['products', 'Sản phẩm'],
                ['orders', 'Đơn hàng'],
                ['vouchers', 'Mã giảm'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setOwnerTab(key)}
                className={`flex-1 rounded-full py-2 ${
                  ownerTab === key ? 'bg-brand' : 'bg-alias-layer-01'
                }`}>
                <Typography
                  size="small"
                  weight={ownerTab === key ? 'semibold' : 'regular'}
                  className={
                    ownerTab === key ? 'text-alias-background' : undefined
                  }
                  color={ownerTab === key ? undefined : 'text-secondary'}>
                  {label}
                </Typography>
              </button>
            ))}
          </div>
          {ownerTab === 'products' ? (
            <OwnerProducts
              products={mine}
              onAdd={() => setProductForm(null)}
              onEdit={p => setProductForm(p)}
            />
          ) : ownerTab === 'orders' ? (
            <SellerOrders />
          ) : (
            <SellerVouchers />
          )}
        </>
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-10 text-center">
          <span className="text-4xl">📦</span>
          <Typography size="small" color="text-secondary">
            Cửa hàng chưa có sản phẩm nào.
          </Typography>
        </div>
      ) : (
        <>
          {/* One category has nothing to filter; more than one gets a chip
              row that narrows the storefront to a single category grid. */}
          {sections.length > 1 && (
            <div className="-mx-1 flex gap-2 overflow-x-auto px-4 pb-1 pt-1">
              {[{ key: 'all', label: 'Tất cả' }, ...sections].map(chip => (
                <button
                  key={chip.key}
                  type="button"
                  onClick={() => setCatFilter(chip.key)}
                  className={`shrink-0 rounded-full px-3 py-1.5 ${
                    catFilter === chip.key ? 'bg-brand' : 'bg-alias-layer-01'
                  }`}>
                  <Typography
                    size="small"
                    weight={catFilter === chip.key ? 'semibold' : 'regular'}
                    className={
                      catFilter === chip.key ? 'text-alias-background' : undefined
                    }
                    color={catFilter === chip.key ? undefined : 'text-secondary'}>
                    {chip.label}
                  </Typography>
                </button>
              ))}
            </div>
          )}
          {catFilter === 'all' ? (
            shownSections.map(section => (
              <ProductStrip
                key={section.label}
                title={section.label}
                products={section.items}
              />
            ))
          ) : (
            <ProductGridSection products={shownSections[0]?.items ?? []} />
          )}
        </>
      )}

      <Sheet open={editingShop} onBackdropClick={() => setEditingShop(false)}>
        <SheetHeader title="Sửa cửa hàng" />
        <SheetBody>
          <div className="pb-2">
            <ShopForm
              shop={shop}
              onSaved={() => {
                setEditingShop(false);
                loadShop();
              }}
            />
          </div>
        </SheetBody>
      </Sheet>

      {productForm !== undefined && (
        <ProductFormSheet
          open
          product={productForm ?? undefined}
          onClose={() => setProductForm(undefined)}
          onSaved={() => {
            setProductForm(undefined);
            refreshMine();
          }}
        />
      )}
    </div>
  );
};

const OwnerProducts = ({
  products,
  onAdd,
  onEdit,
}: {
  products: ApiProduct[];
  onAdd: () => void;
  onEdit: (product: ApiProduct) => void;
}) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center justify-between px-4">
      <Typography size="base" weight="bold">
        Sản phẩm của bạn
      </Typography>
      <Button shape="pill" type="solid-subtle" theme="brand" size="medium" onClick={onAdd}>
        <span className="flex items-center gap-1">
          <Icon name="plus" size={16} />
          Thêm
        </span>
      </Button>
    </div>

    {products.length === 0 ? (
      <div className="flex flex-col items-center gap-2 px-8 pt-6 text-center">
        <span className="text-4xl">📦</span>
        <Typography size="small" color="text-secondary">
          Chưa có sản phẩm nào. Bấm "Thêm" để đăng bán.
        </Typography>
      </div>
    ) : (
      <div className="mx-3 flex flex-col gap-2">
        {products.map(product => (
          <button
            key={product.id}
            type="button"
            onClick={() => onEdit(product)}
            className="flex items-center gap-3 rounded-2xl bg-alias-background p-2.5 text-left shadow-sm active:bg-alias-layer-01">
            <Image
              src={product.imageUrl ?? undefined}
              alt={product.name}
              fit="cover"
              className="size-14 shrink-0 rounded-lg"
              fallback={
                <div className="flex size-14 shrink-0 items-center justify-center rounded-lg bg-global-neutral-neutral-10 text-2xl">
                  🛒
                </div>
              }
            />
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="flex items-center gap-2">
                <Typography size="small" weight="semibold" className="truncate">
                  {product.name}
                </Typography>
                {product.status === 'HIDDEN' && (
                  <span className="shrink-0 rounded bg-alias-layer-01 px-1.5 py-0.5">
                    <Typography size="2x-small" color="text-tertiary">
                      Đang ẩn
                    </Typography>
                  </span>
                )}
              </span>
              <Typography size="small" weight="bold" className="text-brand">
                {formatVnd(product.price)}
              </Typography>
              <Typography size="2x-small" color="text-tertiary">
                Tồn kho: {product.stock}
              </Typography>
            </div>
            <Icon name="pen" size={16} color="text-tertiary" />
          </button>
        ))}
      </div>
    )}
  </div>
);

const ShopSkeleton = () => (
  <div className="pt-chrome flex flex-col gap-2 bg-alias-layer-01">
    <Skeleton className="h-40 w-full" />
    <div className="mx-3 flex flex-col gap-2 rounded-2xl bg-alias-background p-4">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
    <Skeleton className="mx-3 h-44 rounded-2xl" />
  </div>
);

const NotFound = () => {
  const navigate = useNavigate();
  return (
    <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
      <Icon name="office" size={48} color="text-tertiary" />
      <Typography size="large" weight="semibold">
        Không tìm thấy cửa hàng
      </Typography>
      <Button shape="pill" type="outline" onClick={() => navigate('/')}>
        Về trang chủ
      </Button>
    </div>
  );
};

export default ShopPage;
