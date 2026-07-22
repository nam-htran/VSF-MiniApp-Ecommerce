import { Button, Icon, Typography, useNavigate } from '@v-miniapp/ui-react';

const OrdersPage = () => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center gap-3 px-8 pt-24 text-center">
      <Icon name="receipt" size={48} color="text-tertiary" />
      <Typography size="large" weight="semibold">
        Chưa có đơn hàng nào
      </Typography>
      {/* An empty state must offer a way out, not just state a fact. */}
      <Typography size="small" color="text-secondary">
        Đơn hàng của bạn sẽ hiện ở đây sau khi đặt mua.
      </Typography>
      <Button type="outline" onClick={() => navigate('/')}>
        Xem cửa hàng
      </Button>
    </div>
  );
};

export default OrdersPage;
