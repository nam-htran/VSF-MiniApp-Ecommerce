import {
  Icon,
  Sheet,
  SheetBody,
  SheetHeader,
  Typography,
} from '@v-miniapp/ui-react';
import type { VoucherOffer } from '@/api/orders';
import { formatVnd } from '@/lib/format';

/**
 * The shop's vouchers at checkout. Every one is listed, including the ones
 * that don't bite yet — those come back greyed, unselectable, and carrying
 * the reason ("Cần thêm 400.000₫"), because a voucher the buyer can't see
 * is a voucher they can't work towards.
 *
 * The server decides `applicable`; this only draws it. Picking nothing
 * leaves the best voucher applying itself.
 */
export const VoucherSheet = ({
  open,
  offers,
  selected,
  onPick,
  onClose,
}: {
  open: boolean;
  offers: VoucherOffer[];
  /** Code currently applied to this shop, if any. */
  selected: string | null;
  /** null = go back to letting the best one apply itself. */
  onPick: (code: string | null) => void;
  onClose: () => void;
}) => (
  <Sheet open={open} onBackdropClick={onClose}>
    <SheetHeader title="Mã giảm giá của shop" />
    <SheetBody>
      <div className="flex flex-col gap-2 pb-3">
        {offers.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <span className="text-3xl">🎟️</span>
            <Typography size="small" color="text-secondary">
              Shop chưa có mã nào đang chạy.
            </Typography>
          </div>
        ) : (
          <>
            {offers.map(offer => (
              <VoucherRow
                key={offer.code}
                offer={offer}
                selected={offer.code === selected}
                onPick={() => onPick(offer.code)}
              />
            ))}
            {selected && (
              <button
                type="button"
                onClick={() => onPick(null)}
                className="self-center py-2">
                <Typography size="small" className="text-brand">
                  Bỏ chọn, dùng mã tốt nhất
                </Typography>
              </button>
            )}
          </>
        )}
      </div>
    </SheetBody>
  </Sheet>
);

const VoucherRow = ({
  offer,
  selected,
  onPick,
}: {
  offer: VoucherOffer;
  selected: boolean;
  onPick: () => void;
}) => (
  <button
    type="button"
    // Unusable vouchers stay on screen but refuse the tap — the greying is
    // the message, and disabling it keeps the message honest.
    disabled={!offer.applicable}
    onClick={onPick}
    className={`flex items-center gap-3 rounded-xl border p-3 text-left ${
      selected
        ? 'border-brand bg-global-red-red-10'
        : 'border-alias-border-subtle-01 bg-alias-background'
    } ${offer.applicable ? '' : 'opacity-45'}`}>
    <Icon
      name="discount-code"
      size={20}
      className={offer.applicable ? 'shrink-0 text-brand' : 'shrink-0'}
      color={offer.applicable ? undefined : 'text-tertiary'}
    />

    <div className="flex min-w-0 flex-1 flex-col">
      <Typography size="small" weight="semibold" className="truncate">
        {offer.code}
      </Typography>
      <Typography size="2x-small" color="text-secondary" className="line-clamp-2">
        {offer.description}
      </Typography>
      {offer.reason ? (
        <Typography size="2x-small" className="text-global-amber-amber-70">
          {offer.reason}
        </Typography>
      ) : (
        <Typography size="2x-small" weight="semibold" className="text-global-green-green-70">
          Giảm {formatVnd(offer.discount)}
        </Typography>
      )}
    </div>

    {selected && (
      <Icon name="circle-check" type="fill" size={20} className="shrink-0 text-brand" />
    )}
  </button>
);
