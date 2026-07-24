import { useRef, useState } from 'react';
import {
  Button,
  Dialog,
  Dropdown,
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
import { CATEGORIES } from '@/lib/categories';
import { VariantEditor, type DraftVariant } from '@/components/variant-editor';
import {
  createProduct,
  deleteProduct,
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
  const [sku, setSku] = useState(product?.sku ?? '');
  // Options the seller has defined. Empty = a plain product, and `stock`
  // above is what counts; otherwise stock lives only on these.
  const [variants, setVariants] = useState<DraftVariant[]>(
    () =>
      product?.variants?.map(v => ({
        options: v.options,
        stock: v.stock,
        price: v.price,
      })) ?? []
  );
  const [images, setImages] = useState<string[]>(
    product?.imageUrls ?? (product?.imageUrl ? [product.imageUrl] : [])
  );
  const [category, setCategory] = useState<string | undefined>(
    product?.category ?? undefined
  );
  const [hidden, setHidden] = useState(product?.status === 'HIDDEN');

  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Which fields to show an error for. A field earns its error once the
  // seller has left it (blur), or once they press the button with the form
  // still incomplete — never on a pristine field they haven't reached yet.
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const touch = (field: string) =>
    setTouched(prev => (prev[field] ? prev : { ...prev, [field]: true }));

  // VND is whole đồng, and sellers type prices with separators — "50.000",
  // "50,000", "50 000". Number("50,000") is NaN; keep the digits and read
  // them as one number so every way of writing a price works.
  const parseVnd = (s: string): number => {
    const digits = s.replace(/\D/g, '');
    return digits ? Number(digits) : NaN;
  };

  const priceNum = parseVnd(price);
  const originalNum = original.trim() ? parseVnd(original) : null;
  const stockNum = parseVnd(stock);
  // With options, the per-combination quantities are the stock and the field
  // above is disabled; send 0 rather than NaN for the product's own figure.
  const stockValue = Number.isFinite(stockNum) ? stockNum : 0;
  const hasVariants = variants.length > 0;

  // One check per field, each returning its own message. Checked live on
  // every keystroke, like an email box flagging a missing @ — so the seller
  // is corrected while typing, not left to guess at a dead button.
  const errors: Record<string, string | undefined> = {
    name: name.trim().length < 1 ? 'Nhập tên sản phẩm' : undefined,
    description:
      description.trim().length < 1 ? 'Nhập mô tả sản phẩm' : undefined,
    price: !price.trim()
      ? 'Nhập giá bán'
      : !Number.isFinite(priceNum) || priceNum <= 0
        ? 'Giá bán phải lớn hơn 0'
        : undefined,
    stock: hasVariants
      ? undefined
      : !stock.trim()
        ? 'Nhập tồn kho'
        : !Number.isInteger(stockNum) || stockNum < 0
          ? 'Tồn kho phải là số nguyên ≥ 0'
          : undefined,
    original:
      originalNum !== null &&
      (!Number.isFinite(originalNum) || originalNum <= priceNum)
        ? 'Giá gốc phải lớn hơn giá bán, hoặc để trống'
        : undefined,
  };

  /** The message to render under a field: only once it's been seen. */
  const shownError = (field: string): string | undefined =>
    touched[field] || submitted ? errors[field] : undefined;

  const valid = !Object.values(errors).some(Boolean);

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

  const remove = async () => {
    if (!editing || deleting) return;
    setDeleting(true);
    try {
      const { outcome } = await deleteProduct(product.id);
      Toast.show({
        type: 'positive',
        // The server archives instead of deleting when the product has been
        // ordered — say so, so the seller isn't confused to still see it on
        // an old order.
        message:
          outcome === 'archived'
            ? 'Đã gỡ khỏi cửa hàng (vẫn giữ trong đơn đã bán)'
            : 'Đã xoá sản phẩm',
        position: 'bottom',
      });
      setConfirmDelete(false);
      onSaved();
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không xoá được',
        position: 'bottom',
      });
    } finally {
      setDeleting(false);
    }
  };

  const save = async () => {
    if (saving) return;
    // Pressing the button is itself a request to be told what's wrong: reveal
    // every field's error at once rather than staying inert.
    if (!valid) {
      setSubmitted(true);
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateProduct(product.id, {
          sku: sku.trim() || null,
          name: name.trim(),
          description: description.trim(),
          price: priceNum,
          stock: stockValue,
          category: category ?? null,
          imageUrls: images,
          status: hidden ? 'HIDDEN' : 'ACTIVE',
          // Always sent when editing: an empty list is how a seller removes
          // options and goes back to a single stock figure.
          variants: variants.map(v => ({
            options: v.options,
            stock: v.stock,
            price: v.price ?? null,
          })),
        });
      } else {
        await createProduct({
          sku: sku.trim() || null,
          name: name.trim(),
          description: description.trim(),
          unit: unit.trim() || null,
          price: priceNum,
          originalPrice: originalNum,
          stock: stockValue,
          category: category ?? null,
          imageUrls: images,
          // Omitted when there are none, so a plain product is created
          // exactly as before.
          variants: variants.length
            ? variants.map(v => ({
                options: v.options,
                stock: v.stock,
                price: v.price ?? null,
              }))
            : undefined,
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

          <TextField
            value={name}
            onChange={setName}
            onBlur={() => touch('name')}
            placeholder="Tên sản phẩm"
            error={!!shownError('name')}
            errorMessage={shownError('name')}
          />
          <TextField
            value={description}
            onChange={setDescription}
            onBlur={() => touch('description')}
            placeholder="Mô tả"
            error={!!shownError('description')}
            errorMessage={shownError('description')}
          />
          <Dropdown
            placeholder="Danh mục"
            sheetTitle="Chọn danh mục"
            options={CATEGORIES.map(c => ({
              value: c.key,
              label: `${c.emoji}  ${c.label}`,
            }))}
            value={category}
            onChange={setCategory}
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
            onBlur={() => touch('price')}
            placeholder="Giá bán (₫)"
            inputMode="numeric"
            error={!!shownError('price')}
            errorMessage={shownError('price')}
          />
          {!editing && (
            <TextField
              value={original}
              onChange={setOriginal}
              onBlur={() => touch('original')}
              placeholder="Giá gốc nếu đang giảm (₫) — không bắt buộc"
              inputMode="numeric"
              error={!!shownError('original')}
              errorMessage={shownError('original')}
            />
          )}
          {/* The seller's own article number, for reconciling against
              their stock book. Unique inside this shop; another shop may
              use the same code. */}
          <TextField
            value={sku}
            onChange={setSku}
            placeholder="Mã SKU (không bắt buộc)"
          />
          <TextField
            value={stock}
            onChange={setStock}
            onBlur={() => touch('stock')}
            placeholder="Tồn kho"
            inputMode="numeric"
            // Once options exist their quantities are the stock, so this
            // field would be a second number nobody reads.
            disabled={variants.length > 0}
            error={!!shownError('stock')}
            errorMessage={shownError('stock')}
          />
          {variants.length > 0 && (
            <Typography size="2x-small" color="text-tertiary">
              Tồn kho lấy theo từng phân loại bên dưới (tổng{' '}
              {variants.reduce((sum, v) => sum + v.stock, 0)}).
            </Typography>
          )}

          <VariantEditor value={variants} onChange={setVariants} />

          {originalNum !== null &&
            Number.isFinite(originalNum) &&
            originalNum > priceNum && (
              <Typography size="2x-small" color="text-secondary">
                Đang giảm từ {formatVnd(originalNum)} còn {formatVnd(priceNum)}.
              </Typography>
            )}

          {editing && (
            <>
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

              {/* Delete is destructive, so it sits apart from the fields and
                  behind a confirm. Hiding is the softer option right above —
                  a seller who only wants it off the shop has that already. */}
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="mt-1 flex items-center gap-2 border-t border-alias-border-subtle-01 pt-3">
                <Icon name="trash" size={18} className="text-global-red-red-60" />
                <Typography size="small" className="text-global-red-red-60">
                  Xoá sản phẩm
                </Typography>
              </button>
            </>
          )}
        </div>
      </SheetBody>
      <SheetFooter>
        {/* Each field flags its own problem inline; this only nudges the
            seller to look up when they press the button with errors still
            open — some may have scrolled out of view. */}
        {submitted && !valid && !uploading && (
          <div className="mb-2 flex items-center gap-1.5">
            <Icon name="circle-info" size={14} className="shrink-0 text-global-amber-amber-70" />
            <Typography size="2x-small" className="text-global-amber-amber-70">
              Vui lòng kiểm tra các ô được tô đỏ ở trên.
            </Typography>
          </div>
        )}
        <div className="flex w-full gap-2">
          <Button shape="pill" type="outline" theme="neutral" block onClick={onClose}>
            Huỷ
          </Button>
          <Button
            shape="pill"
            type="solid"
            theme="brand"
            block
            loading={saving}
            // Not gated on `valid`: a disabled button can't be pressed, and
            // pressing it is how the seller asks what's wrong. save() checks
            // validity and reveals the errors. Only an in-flight image upload
            // blocks it — its URL isn't ready to save yet.
            disabled={uploading}
            onClick={save}>
            {editing ? 'Lưu' : 'Thêm'}
          </Button>
        </div>
      </SheetFooter>

      {/* Confirm before deleting. portal so it layers above this sheet
          rather than being clipped inside it. */}
      <Dialog
        portal
        open={confirmDelete}
        title="Xoá sản phẩm?"
        description={`"${name || product?.name || 'Sản phẩm này'}" sẽ bị gỡ khỏi cửa hàng. Nếu đã từng bán, sản phẩm vẫn được giữ trong các đơn cũ.`}
        onBackdropClick={() => !deleting && setConfirmDelete(false)}
        footer={
          <div className="flex w-full gap-2">
            <Button
              shape="pill"
              type="outline"
              theme="neutral"
              block
              disabled={deleting}
              onClick={() => setConfirmDelete(false)}>
              Huỷ
            </Button>
            <Button
              shape="pill"
              type="solid"
              theme="brand"
              block
              loading={deleting}
              onClick={remove}>
              Xoá
            </Button>
          </div>
        }
      />
    </Sheet>
  );
};
