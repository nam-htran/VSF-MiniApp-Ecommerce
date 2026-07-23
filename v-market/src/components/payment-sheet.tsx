import { useState } from 'react';
import {
  Button,
  Icon,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import { abandonPayment, confirmPayment } from '@/api/payments';
import { formatVnd } from '@/lib/format';

/**
 * The V-App payment sheet, simulated. On a real device initPayment opens
 * the platform's own; here it's this. Confirming asks the gateway to
 * charge, which sends the IPN that flips the order to PAID — the client
 * never marks its own order paid.
 *
 * It reports the outcome up via onClose('paid' | 'cancelled') and leaves
 * navigation to the caller: checkout goes to the orders list, the order
 * detail refetches in place.
 */
export const PaymentSheet = ({
  paymentId,
  amount,
  onClose,
}: {
  paymentId: string;
  amount: number;
  onClose: (result: 'paid' | 'cancelled') => void;
}) => {
  const [busy, setBusy] = useState<'pay' | 'cancel' | null>(null);

  const pay = async () => {
    setBusy('pay');
    try {
      await confirmPayment(paymentId);
      Toast.show({
        type: 'positive',
        message: 'Thanh toán thành công',
        position: 'bottom',
      });
      onClose('paid');
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Thanh toán chưa xong, thử lại nhé',
        position: 'bottom',
      });
      setBusy(null);
    }
  };

  const cancel = async () => {
    setBusy('cancel');
    try {
      await abandonPayment(paymentId);
    } catch {
      /* the order stays PENDING regardless */
    }
    Toast.show({
      type: 'informative',
      message: 'Đã huỷ thanh toán — đơn đang chờ trong Đơn hàng',
      position: 'bottom',
    });
    onClose('cancelled');
  };

  return (
    <Sheet open onBackdropClick={busy ? undefined : cancel}>
      <SheetHeader title="Cổng thanh toán V-App" />
      <SheetBody>
        <div className="flex flex-col items-center gap-2 py-2 text-center">
          <Icon name="wallet" size={32} className="text-brand" />
          <Typography size="small" color="text-secondary">
            Số tiền thanh toán
          </Typography>
          <Typography size="2x-large" weight="bold" className="text-brand">
            {formatVnd(amount)}
          </Typography>
          <Typography size="2x-small" color="text-tertiary">
            Cổng thanh toán V-App (giả lập). Trên máy thật đây là màn hình
            thanh toán của nền tảng.
          </Typography>
        </div>
      </SheetBody>
      <SheetFooter>
        <div className="flex w-full gap-2">
          <Button
            shape="pill"
            type="outline"
            theme="neutral"
            block
            loading={busy === 'cancel'}
            onClick={cancel}>
            Huỷ
          </Button>
          <Button
            shape="pill"
            type="solid"
            theme="brand"
            block
            loading={busy === 'pay'}
            onClick={pay}>
            Thanh toán
          </Button>
        </div>
      </SheetFooter>
    </Sheet>
  );
};
