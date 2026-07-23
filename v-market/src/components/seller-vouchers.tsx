import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  DateField,
  Dropdown,
  Icon,
  Sheet,
  SheetBody,
  SheetHeader,
  Skeleton,
  TextField,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import {
  createVoucher,
  listMyVouchers,
  setVoucherStatus,
  type Voucher,
} from '@/api/vouchers';
import { CATEGORIES } from '@/lib/categories';
import { formatVnd } from '@/lib/format';

/**
 * The owner's sales. Lists every voucher the shop has ever run — expired
 * ones included, because a seller wants to see what they did last month —
 * and creates new ones.
 *
 * Nothing here decides a discount: the server does that, with the same code
 * that prices the cards and the orders. This screen only writes the rule.
 */

/** What state a voucher is in right now, for the chip on its card. */
const liveness = (voucher: Voucher) => {
  const now = Date.now();
  if (voucher.status === 'DISABLED')
    return { label: 'Đã tắt', tone: 'bg-alias-layer-01 text-text-tertiary' };
  if (new Date(voucher.endsAt).getTime() <= now)
    return { label: 'Hết hạn', tone: 'bg-alias-layer-01 text-text-tertiary' };
  if (new Date(voucher.startsAt).getTime() > now)
    return {
      label: 'Chưa bắt đầu',
      tone: 'bg-global-amber-amber-10 text-global-amber-amber-70',
    };
  return {
    label: 'Đang chạy',
    tone: 'bg-global-green-green-10 text-global-green-green-70',
  };
};

const summarise = (voucher: Voucher) => {
  const head =
    voucher.discountType === 'PERCENT'
      ? `Giảm ${voucher.discountValue}%`
      : `Giảm ${formatVnd(voucher.discountValue)}`;
  const cap =
    voucher.discountType === 'PERCENT' && voucher.maxDiscount
      ? `, tối đa ${formatVnd(voucher.maxDiscount)}`
      : '';
  const floor =
    voucher.minOrder > 0 ? ` · đơn từ ${formatVnd(voucher.minOrder)}` : '';
  return `${head}${cap}${floor}`;
};

const categoryLabel = (key: string | null) =>
  key === null
    ? 'Toàn shop'
    : (CATEGORIES.find(c => c.key === key)?.label ?? key);

export const SellerVouchers = () => {
  const [vouchers, setVouchers] = useState<Voucher[] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    listMyVouchers()
      .then(page => setVouchers(page.items))
      .catch(() => setVouchers([]));
  }, []);

  useEffect(load, [load]);

  const toggle = async (voucher: Voucher) => {
    if (busy) return;
    setBusy(voucher.id);
    const next = voucher.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    try {
      const updated = await setVoucherStatus(voucher.id, next);
      setVouchers(prev =>
        prev ? prev.map(v => (v.id === updated.id ? updated : v)) : prev
      );
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không đổi được',
        position: 'bottom',
      });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between px-4">
        <Typography size="base" weight="bold">
          Mã giảm giá
        </Typography>
        <Button
          shape="pill"
          type="solid-subtle"
          theme="brand"
          size="medium"
          onClick={() => setFormOpen(true)}>
          <span className="flex items-center gap-1">
            <Icon name="plus" size={16} />
            Tạo mã
          </span>
        </Button>
      </div>

      {vouchers === null ? (
        <div className="flex flex-col gap-2 px-3">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
        </div>
      ) : vouchers.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-8 text-center">
          <span className="text-4xl">🎟️</span>
          <Typography size="small" color="text-secondary">
            Chưa có mã nào. Tạo một mã để chạy khuyến mãi cho shop.
          </Typography>
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-3">
          {vouchers.map(voucher => {
            const state = liveness(voucher);
            return (
              <div
                key={voucher.id}
                className="flex flex-col gap-2 rounded-2xl bg-alias-background p-3 shadow-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <Icon
                      name="discount-code"
                      size={16}
                      className="shrink-0 text-brand"
                    />
                    <Typography size="small" weight="bold" className="truncate">
                      {voucher.code}
                    </Typography>
                  </span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 ${state.tone}`}>
                    <Typography size="2x-small" weight="semibold">
                      {state.label}
                    </Typography>
                  </span>
                </div>

                <Typography size="x-small" color="text-secondary">
                  {voucher.description}
                </Typography>
                <Typography size="2x-small" color="text-tertiary">
                  {summarise(voucher)} · {categoryLabel(voucher.category)}
                </Typography>
                <Typography size="2x-small" color="text-tertiary">
                  {new Date(voucher.startsAt).toLocaleDateString('vi-VN')} –{' '}
                  {new Date(voucher.endsAt).toLocaleDateString('vi-VN')}
                </Typography>

                <Button
                  shape="pill"
                  type="outline"
                  size="medium"
                  block
                  loading={busy === voucher.id}
                  onClick={() => toggle(voucher)}>
                  {voucher.status === 'ACTIVE' ? 'Tắt mã' : 'Bật lại'}
                </Button>
              </div>
            );
          })}
        </div>
      )}

      <VoucherFormSheet
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onCreated={() => {
          setFormOpen(false);
          load();
        }}
      />
    </div>
  );
};

const inDays = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
};

const VoucherFormSheet = ({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) => {
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [type, setType] = useState<'PERCENT' | 'AMOUNT'>('PERCENT');
  const [value, setValue] = useState('');
  const [maxDiscount, setMaxDiscount] = useState('');
  const [minOrder, setMinOrder] = useState('');
  const [startsAt, setStartsAt] = useState<Date | null>(new Date());
  const [endsAt, setEndsAt] = useState<Date | null>(inDays(7));
  const [saving, setSaving] = useState(false);

  const numeric = Number(value);
  const valid =
    code.trim().length >= 3 &&
    description.trim().length >= 1 &&
    numeric > 0 &&
    (type !== 'PERCENT' || numeric <= 100) &&
    startsAt !== null &&
    endsAt !== null &&
    endsAt.getTime() > startsAt.getTime();

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    try {
      await createVoucher({
        code: code.trim().toUpperCase(),
        description: description.trim(),
        // The dropdown's "Toàn shop" is the absence of a category.
        category: category || null,
        discountType: type,
        discountValue: numeric,
        maxDiscount: type === 'PERCENT' && maxDiscount ? Number(maxDiscount) : null,
        minOrder: minOrder ? Number(minOrder) : 0,
        startsAt: startsAt!.toISOString(),
        endsAt: endsAt!.toISOString(),
      });
      Toast.show({ type: 'positive', message: 'Đã tạo mã', position: 'bottom' });
      setCode('');
      setDescription('');
      setValue('');
      setMaxDiscount('');
      setMinOrder('');
      onCreated();
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không tạo được mã',
        position: 'bottom',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onBackdropClick={saving ? undefined : onClose}>
      <SheetHeader title="Tạo mã giảm giá" />
      <SheetBody>
        <div className="flex flex-col gap-3 pb-3">
          <TextField
            value={code}
            onChange={v => setCode(v.toUpperCase())}
            placeholder="Mã, ví dụ SALE20 (ít nhất 3 ký tự)"
          />
          <TextField
            value={description}
            onChange={setDescription}
            placeholder="Mô tả hiện cho người mua"
          />

          {/* Scope. Leaving it on "Toàn shop" means every item the shop
              sells; a category also narrows what min_order is measured on. */}
          <Dropdown
            placeholder="Áp dụng cho"
            sheetTitle="Áp dụng cho"
            options={[
              { value: '', label: 'Toàn shop' },
              ...CATEGORIES.map(c => ({ value: c.key, label: c.label })),
            ]}
            value={category ?? ''}
            onChange={setCategory}
          />

          <div className="flex gap-2">
            {(
              [
                ['PERCENT', 'Giảm %'],
                ['AMOUNT', 'Giảm tiền'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setType(key)}
                className={`flex-1 rounded-full py-2 ${
                  type === key ? 'bg-brand' : 'bg-alias-layer-01'
                }`}>
                <Typography
                  size="small"
                  weight={type === key ? 'semibold' : 'regular'}
                  className={type === key ? 'text-alias-background' : undefined}
                  color={type === key ? undefined : 'text-secondary'}>
                  {label}
                </Typography>
              </button>
            ))}
          </div>

          <TextField
            value={value}
            onChange={setValue}
            inputMode="numeric"
            placeholder={type === 'PERCENT' ? 'Phần trăm giảm (1–100)' : 'Số tiền giảm'}
          />
          {type === 'PERCENT' && (
            <TextField
              value={maxDiscount}
              onChange={setMaxDiscount}
              inputMode="numeric"
              placeholder="Giảm tối đa (để trống = không giới hạn)"
            />
          )}
          <TextField
            value={minOrder}
            onChange={setMinOrder}
            inputMode="numeric"
            placeholder="Đơn tối thiểu (để trống = không yêu cầu)"
          />

          <DateField
            label={{ children: 'Bắt đầu' }}
            value={startsAt}
            onChange={setStartsAt}
          />
          <DateField
            label={{ children: 'Kết thúc' }}
            value={endsAt}
            onChange={setEndsAt}
          />

          <Button
            shape="pill"
            type="solid"
            theme="brand"
            block
            loading={saving}
            disabled={!valid}
            onClick={save}>
            Tạo mã
          </Button>
        </div>
      </SheetBody>
    </Sheet>
  );
};
