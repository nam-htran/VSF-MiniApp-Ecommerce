import { useEffect, useState } from 'react';
import { Carousel, CarouselItem, Icon, Typography } from '@v-miniapp/ui-react';
import { listVouchers, type Voucher } from '@/api/vouchers';
import { formatVnd } from '@/lib/format';

/**
 * Rotating promo header: a brand block bleeding to the top edge, then a
 * carousel of the sales actually running, straight from the database.
 *
 * Nothing here is written by hand any more. A voucher appears because it is
 * live and disappears the moment it expires — the server only ever returns
 * vouchers inside their window, so the strip needs no cleanup and can never
 * advertise a sale that has ended. Autoplay comes from the library's embla
 * integration, not a hand-rolled timer.
 */

/** "còn 3 ngày" / "còn 5 giờ" — urgency, at the resolution that matters. */
const remaining = (endsAt: string): string => {
  const ms = new Date(endsAt).getTime() - Date.now();
  if (ms <= 0) return 'sắp kết thúc';
  const hours = Math.floor(ms / 3_600_000);
  if (hours < 1) return 'còn chưa đầy 1 giờ';
  if (hours < 24) return `còn ${hours} giờ`;
  return `còn ${Math.floor(hours / 24)} ngày`;
};

const headline = (voucher: Voucher): string =>
  voucher.discountType === 'PERCENT'
    ? `Giảm ${voucher.discountValue}%`
    : `Giảm ${formatVnd(voucher.discountValue)}`;

export const PromoSection = () => {
  const [vouchers, setVouchers] = useState<Voucher[]>([]);

  useEffect(() => {
    listVouchers()
      .then(page => setVouchers(page.items))
      .catch(() => setVouchers([]));
  }, []);

  return (
    <section className="pt-chrome flex flex-col gap-2 bg-brand px-4 pb-3">
      {vouchers.length === 0 ? (
        // No sale running: say so plainly rather than inventing one. Keeps
        // the block the same height so the page below doesn't jump.
        <div className="flex flex-col">
          <Typography size="x-small" weight="bold" className="text-white/85">
            V-Market
          </Typography>
          <Typography
            size="2x-large"
            weight="bold"
            component="h2"
            className="text-global-basic-white">
            Đi chợ online
          </Typography>
          <Typography size="small" className="text-white/80">
            Chưa có khuyến mãi nào đang chạy
          </Typography>
        </div>
      ) : (
        /* align 'start', not the default 'center' — centred slides sit off
           the left edge and let the next slide peek in on the right. */
        <Carousel
          options={{
            autoplay: true,
            delay: 5000,
            loop: true,
            align: 'start',
            gap: 0,
          }}>
          {vouchers.map(voucher => (
            <CarouselItem key={voucher.id} width="100%">
              {/* Same line count on every slide, so autoHeight never makes
                  the block jump while rotating. */}
              <div className="flex flex-col">
                <span className="flex items-center gap-1.5">
                  <Icon
                    name="discount-code"
                    size={12}
                    className="shrink-0 text-global-basic-white"
                  />
                  <Typography
                    size="x-small"
                    weight="bold"
                    className="truncate text-white/85">
                    {voucher.code} · {remaining(voucher.endsAt)}
                  </Typography>
                </span>
                <Typography
                  size="2x-large"
                  weight="bold"
                  component="h2"
                  className="text-global-basic-white">
                  {headline(voucher)}
                </Typography>
                <Typography size="small" className="line-clamp-1 text-white/80">
                  {voucher.description}
                </Typography>
              </div>
            </CarouselItem>
          ))}
        </Carousel>
      )}
    </section>
  );
};
