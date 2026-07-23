import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Icon,
  Skeleton,
  Toast,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  listPaymentExceptions,
  resolvePaymentException,
  type PaymentExceptionView,
} from '@/api/payments';
import { useSession } from '@/lib/auth';
import { formatVnd } from '@/lib/format';

/**
 * The refund queue: money the marketplace received but could not apply to
 * an order — a payment that arrived after its order was cancelled, an
 * amount that didn't match, an order that never existed.
 *
 * Every row here is somebody out of pocket. Recording them was the easy
 * part; this screen exists because a debt nobody can see is a debt nobody
 * pays.
 *
 * Operator-only. Nothing on this page moves money: there is no treasury
 * and the mock gateway has no refund call. "Đã hoàn tiền" records that a
 * human did it, which is what stops the same payment being refunded twice.
 */
const OpsPage = () => {
  const session = useSession();
  const navigate = useNavigate();
  const [rows, setRows] = useState<PaymentExceptionView[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const isOperator = session?.user.role === 'ADMIN';

  const load = useCallback(() => {
    if (!isOperator) return;
    listPaymentExceptions()
      .then(page => setRows(page.items))
      .catch(() => setRows([]));
  }, [isOperator]);

  useEffect(load, [load]);

  const resolve = async (entry: PaymentExceptionView) => {
    if (busy) return;
    setBusy(entry.id);
    try {
      await resolvePaymentException(entry.id);
      setRows(prev => (prev ? prev.filter(r => r.id !== entry.id) : prev));
      Toast.show({
        type: 'positive',
        message: 'Đã đánh dấu hoàn tiền',
        position: 'bottom',
      });
    } catch (error) {
      Toast.show({
        type: 'negative',
        message: error instanceof Error ? error.message : 'Không cập nhật được',
        position: 'bottom',
      });
    } finally {
      setBusy(null);
    }
  };

  if (!isOperator) {
    return (
      <div className="pt-chrome-hero flex flex-col items-center gap-3 px-8 text-center">
        <Icon name="lock" size={44} color="text-tertiary" />
        <Typography size="large" weight="semibold">
          Chỉ dành cho người vận hành
        </Typography>
        <Typography size="small" color="text-secondary">
          Tài khoản của bạn không có quyền xem đối soát thanh toán.
        </Typography>
        <Button shape="pill" type="outline" onClick={() => navigate('/account')}>
          Quay lại
        </Button>
      </div>
    );
  }

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01 pb-8">
      <div className="px-4 pb-1">
        <Typography size="2x-large" weight="bold" component="h1">
          Đối soát thanh toán
        </Typography>
        <Typography size="x-small" color="text-secondary">
          Tiền đã nhận nhưng chưa gán được vào đơn nào. Hoàn tiền xong thì
          đánh dấu để không hoàn hai lần.
        </Typography>
      </div>

      {rows === null ? (
        <div className="flex flex-col gap-2 px-3">
          <Skeleton className="h-28 w-full rounded-2xl" />
          <Skeleton className="h-28 w-full rounded-2xl" />
        </div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-10 text-center">
          <span className="text-4xl">✅</span>
          <Typography size="small" color="text-secondary">
            Không có khoản nào chờ hoàn. Mọi khoản tiền nhận được đều đã gán
            đúng đơn.
          </Typography>
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-3">
          {rows.map(entry => (
            <div
              key={entry.id}
              className="flex flex-col gap-2 rounded-2xl bg-alias-background p-3 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <Typography size="large" weight="bold" className="text-brand">
                  {formatVnd(entry.amount)}
                </Typography>
                <span className="shrink-0 rounded-full bg-global-amber-amber-10 px-2 py-0.5">
                  <Typography
                    size="2x-small"
                    weight="semibold"
                    className="text-global-amber-amber-70">
                    Chờ hoàn
                  </Typography>
                </span>
              </div>

              <Typography size="x-small" color="text-secondary">
                {entry.reason}
              </Typography>

              {/* The gateway's id, not ours: it is what a refund is issued
                  against, and it still means something once our own order
                  has been cancelled. */}
              <div className="flex flex-col gap-0.5 rounded-lg bg-alias-layer-01 p-2">
                <Typography size="2x-small" color="text-tertiary">
                  Mã giao dịch cổng
                </Typography>
                <Typography size="x-small" className="break-all">
                  {entry.gatewayPaymentId}
                </Typography>
                {entry.orderId && (
                  <>
                    <Typography size="2x-small" color="text-tertiary" className="pt-1">
                      Đơn hàng
                    </Typography>
                    <Typography size="x-small" className="break-all">
                      {entry.orderId}
                    </Typography>
                  </>
                )}
              </div>

              <Button
                shape="pill"
                type="outline"
                size="medium"
                block
                loading={busy === entry.id}
                onClick={() => resolve(entry)}>
                Đã hoàn tiền
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default OpsPage;
