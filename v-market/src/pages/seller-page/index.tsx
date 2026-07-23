import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Icon,
  Image,
  Sheet,
  SheetBody,
  SheetHeader,
  Skeleton,
  Typography,
} from '@v-miniapp/ui-react';
import { getMyShop, type Shop } from '@/api/shops';
import { listMyProducts, type ApiProduct } from '@/api/products';
import { ProductFormSheet } from '@/components/product-form-sheet';
import { ShopForm } from '@/components/shop-form';
import { ApiError } from '@/api/client';
import { formatVnd } from '@/lib/format';

/**
 * The seller channel. Opening a shop is what turns a buyer into a seller,
 * so this screen has two faces: an open-shop form for anyone without one
 * yet, and a shop dashboard — products, add, edit, hide — once there is a
 * shop. Session-guarded; the shop and product endpoints are owner-scoped.
 */
type State =
  | { status: 'loading' }
  | { status: 'noshop' }
  | { status: 'shop'; shop: Shop }
  | { status: 'failed'; message: string };

const SellerPage = () => {
  const [state, setState] = useState<State>({ status: 'loading' });

  const load = useCallback(() => {
    setState({ status: 'loading' });
    getMyShop()
      .then(shop => setState({ status: 'shop', shop }))
      .catch(error => {
        // 403 = logged in but no shop yet: offer to open one.
        if (error instanceof ApiError && error.status === 403) {
          setState({ status: 'noshop' });
        } else {
          setState({
            status: 'failed',
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
  }, []);

  useEffect(load, [load]);

  if (state.status === 'loading') return <SellerSkeleton />;
  if (state.status === 'failed')
    return (
      <div className="pt-chrome px-3">
        <Alert
          type="negative"
          title="Không tải được kênh người bán"
          message={state.message}
          action={<Button onClick={load}>Thử lại</Button>}
        />
      </div>
    );
  if (state.status === 'noshop') return <OpenShop onOpened={load} />;
  return <ShopDashboard shop={state.shop} onShopChanged={load} />;
};

const OpenShop = ({ onOpened }: { onOpened: () => void }) => (
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
    <ShopForm onSaved={onOpened} />
  </div>
);

const ShopDashboard = ({
  shop,
  onShopChanged,
}: {
  shop: Shop;
  onShopChanged: () => void;
}) => {
  const [editing, setEditing] = useState(false);
  const [products, setProducts] = useState<ApiProduct[] | null>(null);
  // undefined = closed; null = creating; a product = editing.
  const [form, setForm] = useState<ApiProduct | null | undefined>(undefined);

  const refresh = useCallback(() => {
    listMyProducts()
      .then(page => setProducts(page.items))
      .catch(() => setProducts([]));
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-3 bg-alias-layer-01 pb-8">
      <div className="mx-3 flex items-center gap-3 rounded-2xl bg-alias-background p-4 shadow-sm">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-global-red-red-05">
          <Icon name="office" size={22} className="text-brand" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <Typography size="large" weight="bold" className="truncate">
            {shop.name}
          </Typography>
          <Typography size="x-small" color="text-secondary" className="line-clamp-1">
            {shop.description}
          </Typography>
          {shop.province && (
            <span className="mt-0.5 flex items-center gap-1">
              <Icon name="pin" size={12} className="shrink-0 text-global-teal-teal-60" />
              <Typography size="2x-small" color="text-tertiary" className="truncate">
                {shop.address ? `${shop.address}, ${shop.province}` : shop.province}
              </Typography>
            </span>
          )}
        </div>
        <button
          type="button"
          aria-label="Sửa cửa hàng"
          onClick={() => setEditing(true)}
          className="shrink-0 self-start p-1">
          <Icon name="pen" size={18} color="text-tertiary" />
        </button>
      </div>

      {!shop.province && (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="mx-3 flex items-center gap-2 rounded-xl border border-dashed border-alias-border-subtle-01 px-3 py-2 text-left">
          <Icon name="triangle-warning" size={16} className="shrink-0 text-global-amber-amber-60" />
          <Typography size="x-small" color="text-secondary" className="flex-1">
            Thêm địa chỉ & tỉnh/thành để hiện thời gian giao dự kiến trên sản phẩm.
          </Typography>
          <Icon name="chevron-right" size={14} color="text-tertiary" />
        </button>
      )}

      <div className="flex items-center justify-between px-4">
        <Typography size="base" weight="bold">
          Sản phẩm
        </Typography>
        <Button type="solid-subtle" theme="brand" size="medium" onClick={() => setForm(null)}>
          <span className="flex items-center gap-1">
            <Icon name="plus" size={16} />
            Thêm
          </span>
        </Button>
      </div>

      {products === null ? (
        <div className="mx-3 flex flex-col gap-2">
          {[0, 1].map(i => (
            <Skeleton key={i} className="h-20 w-full rounded-2xl" />
          ))}
        </div>
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-10 text-center">
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
              onClick={() => setForm(product)}
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
              <Icon name="chevron-right" size={16} color="text-tertiary" />
            </button>
          ))}
        </div>
      )}

      {form !== undefined && (
        <ProductFormSheet
          open
          product={form ?? undefined}
          onClose={() => setForm(undefined)}
          onSaved={() => {
            setForm(undefined);
            refresh();
          }}
        />
      )}

      <Sheet open={editing} onBackdropClick={() => setEditing(false)}>
        <SheetHeader title="Sửa cửa hàng" />
        <SheetBody>
          <div className="pb-2">
            <ShopForm
              shop={shop}
              onSaved={() => {
                setEditing(false);
                onShopChanged();
              }}
            />
          </div>
        </SheetBody>
      </Sheet>
    </div>
  );
};

const SellerSkeleton = () => (
  <div className="pt-chrome flex flex-col gap-3 px-3">
    <Skeleton className="h-20 w-full rounded-2xl" />
    <Skeleton className="h-8 w-32" />
    <Skeleton className="h-20 w-full rounded-2xl" />
  </div>
);

export default SellerPage;
