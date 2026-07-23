import { useRef, useState } from 'react';
import {
  Button,
  Icon,
  Image,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  TextField,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import {
  createProduct,
  updateProduct,
  type ApiProduct,
} from '@/api/products';
import { uploadImage } from '@/api/uploads';
import { formatVnd } from '@/lib/format';

/**
 * Add or edit a product. Create takes the full set of fields; edit patches
 * what the backend allows to change (name, description, price, stock, image
 * and visibility — unit and the sale price are set once, at creation).
 *
 * The image is uploaded to our own origin the moment it's picked — the app
 * can't hotlink a CDN — and the returned URL is what gets saved.
 */
export const ProductFormSheet = ({
  open,
  product,
  onClose,
  onSaved,
}: {
  open: boolean;
  product?: ApiProduct;
  onClose: () => void;
  onSaved: () => void;
}) => {
  const editing = product !== undefined;

  const [name, setName] = useState(product?.name ?? '');
  const [description, setDescription] = useState(product?.description ?? '');
  const [unit, setUnit] = useState(product?.unit ?? '');
  const [price, setPrice] = useState(product ? String(product.price) : '');
  const [original, setOriginal] = useState(
    product?.originalPrice != null ? String(product.originalPrice) : ''
  );
  const [stock, setStock] = useState(product ? String(product.stock) : '');
  const [images, setImages] = useState<string[]>(
    product?.imageUrls ?? (product?.imageUrl ? [product.imageUrl] : [])
  );
  const [hidden, setHidden] = useState(product?.status === 'HIDDEN');

  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const priceNum = Number(price);
  const originalNum = original.trim() ? Number(original) : null;
  const stockNum = Number(stock);

  const valid =
    name.trim().length >= 1 &&
    description.trim().length >= 1 &&
    Number.isFinite(priceNum) &&
    priceNum > 0 &&
    Number.isInteger(stockNum) &&
    stockNum >= 0 &&
    (originalNum === null ||
      (Number.isFinite(originalNum) && originalNum > priceNum));

  const pickImage = async (file: File) => {
    setUploading(true);
    try {
      const url = await uploadImage(file);
      setImages(prev => [...prev, url].slice(0, 8));
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Tải ảnh thất bại',
        position: 'bottom',
      });
    } finally {
      setUploading(false);
    }
  };

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    try {
      if (editing) {
        await updateProduct(product.id, {
          name: name.trim(),
          description: description.trim(),
          price: priceNum,
          stock: stockNum,
          imageUrls: images,
          status: hidden ? 'HIDDEN' : 'ACTIVE',
        });
      } else {
        await createProduct({
          name: name.trim(),
          description: description.trim(),
          unit: unit.trim() || null,
          price: priceNum,
          originalPrice: originalNum,
          stock: stockNum,
          imageUrls: images,
        });
      }
      Toast.show({
        type: 'positive',
        message: editing ? 'Đã cập nhật sản phẩm' : 'Đã thêm sản phẩm',
        position: 'bottom',
      });
      onSaved();
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không lưu được',
        position: 'bottom',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onBackdropClick={saving ? undefined : onClose}>
      <SheetHeader title={editing ? 'Sửa sản phẩm' : 'Thêm sản phẩm'} />
      <SheetBody>
        <div className="flex flex-col gap-3 pb-2">
          {/* gallery: thumbnails + an add tile, up to 8. The first is the
              cover shown on cards. */}
          <div className="flex flex-col gap-1">
            <Typography size="small" weight="semibold">
              Ảnh sản phẩm
            </Typography>
            <Typography size="2x-small" color="text-tertiary">
              Tối đa 8 ảnh. Ảnh đầu tiên là ảnh bìa. JPEG/PNG/WebP, ≤5MB.
            </Typography>
            <div className="mt-1 flex flex-wrap gap-2">
              {images.map((url, i) => (
                <div key={url} className="relative size-20">
                  <Image src={url} alt="" fit="cover" className="size-20 rounded-xl" />
                  {i === 0 && (
                    <span className="absolute bottom-0 left-0 rounded-tr-lg rounded-bl-xl bg-brand px-1.5 py-0.5">
                      <Typography size="2x-small" weight="semibold" className="text-alias-background">
                        Bìa
                      </Typography>
                    </span>
                  )}
                  <button
                    type="button"
                    aria-label="Xoá ảnh"
                    onClick={() => setImages(prev => prev.filter(u => u !== url))}
                    className="absolute -right-1.5 -top-1.5 flex size-5 items-center justify-center rounded-full bg-alias-background shadow">
                    <Icon name="xmark" size={12} color="text-tertiary" />
                  </button>
                </div>
              ))}
              {images.length < 8 && (
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  disabled={uploading}
                  className="flex size-20 shrink-0 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-alias-border-subtle-01 bg-alias-layer-01">
                  {uploading ? (
                    <Icon name="loader" size={20} animation="spin" />
                  ) : (
                    <>
                      <Icon name="plus" size={18} color="text-tertiary" />
                      <Typography size="2x-small" color="text-tertiary">
                        Thêm ảnh
                      </Typography>
                    </>
                  )}
                </button>
              )}
            </div>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={event => {
                const file = event.target.files?.[0];
                if (file) void pickImage(file);
                event.target.value = '';
              }}
            />
          </div>

          <TextField value={name} onChange={setName} placeholder="Tên sản phẩm" />
          <TextField
            value={description}
            onChange={setDescription}
            placeholder="Mô tả"
          />
          {!editing && (
            <TextField
              value={unit}
              onChange={setUnit}
              placeholder="Đơn vị (vd: Hộp 500g) — không bắt buộc"
            />
          )}
          <TextField
            value={price}
            onChange={setPrice}
            placeholder="Giá bán (₫)"
            inputMode="numeric"
          />
          {!editing && (
            <TextField
              value={original}
              onChange={setOriginal}
              placeholder="Giá gốc nếu đang giảm (₫) — không bắt buộc"
              inputMode="numeric"
            />
          )}
          <TextField
            value={stock}
            onChange={setStock}
            placeholder="Tồn kho"
            inputMode="numeric"
          />

          {originalNum !== null &&
            Number.isFinite(originalNum) &&
            originalNum > priceNum && (
              <Typography size="2x-small" color="text-secondary">
                Đang giảm từ {formatVnd(originalNum)} còn {formatVnd(priceNum)}.
              </Typography>
            )}

          {editing && (
            <button
              type="button"
              onClick={() => setHidden(v => !v)}
              className="flex items-center gap-2">
              <Icon
                name={hidden ? 'eye-slash' : 'eye'}
                size={18}
                className={hidden ? 'text-alias-icon-tertiary' : 'text-brand'}
              />
              <Typography size="small">
                {hidden ? 'Đang ẩn khỏi cửa hàng' : 'Đang hiển thị'}
              </Typography>
            </button>
          )}
        </div>
      </SheetBody>
      <SheetFooter>
        <div className="flex w-full gap-2">
          <Button type="outline" theme="neutral" block onClick={onClose}>
            Huỷ
          </Button>
          <Button
            type="solid"
            theme="brand"
            block
            loading={saving}
            disabled={!valid || uploading}
            onClick={save}>
            {editing ? 'Lưu' : 'Thêm'}
          </Button>
        </div>
      </SheetFooter>
    </Sheet>
  );
};
