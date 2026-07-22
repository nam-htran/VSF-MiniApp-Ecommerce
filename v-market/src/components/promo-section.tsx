import { Carousel, CarouselItem, Typography } from '@v-miniapp/ui-react';
import { AddressLine } from './address-line';

/**
 * Rotating promo header: mint block bleeding to the top edge, an address
 * line, then a carousel of claims that advances every 5 seconds (and can
 * be swiped by hand). Autoplay comes from the library's own embla
 * integration — options.autoplay/delay — not a hand-rolled timer.
 *
 * The promo copy is a visual placeholder — vouchers are out of the plan,
 * so nothing in the backend enforces these claims yet. They live in this
 * array and nowhere else.
 */
const PROMOS = [
  {
    eyebrow: 'Bắt đầu tiết kiệm với',
    title: 'Freeship + giảm 10%',
    sub: 'Cho đơn từ 120.000 ₫ tại cửa hàng chọn lọc',
  },
  {
    eyebrow: 'Deal giữa tuần',
    title: 'Giảm 15% đồ tươi sống',
    sub: 'Áp dụng thứ 4 hằng tuần, tối đa 50.000 ₫',
  },
  {
    eyebrow: 'Đi chợ sáng',
    title: '0 ₫ phí giao trước 11h',
    sub: 'Cho đơn đặt trước 9h sáng mỗi ngày',
  },
];

export const PromoSection = () => (
  <section
    className="flex flex-col gap-2 bg-global-teal-teal-10 px-4 pb-3"
    style={{
      // Text starts just below the status bar, in the empty space left of
      // V-App's ⋯ ✕ pill. The 44px fallback stands in for the Simulator's
      // fake status bar; a real device injects the true inset.
      paddingTop: 'calc(var(--safe-area-inset-top, 44px) + 8px)',
    }}>
    <AddressLine />

    {/* align 'start', not the default 'center' — centred slides sit off
        the left edge and let the next slide peek in on the right, so the
        text never lines up with the address line above it. */}
    <Carousel
      options={{ autoplay: true, delay: 5000, loop: true, align: 'start', gap: 0 }}>
      {PROMOS.map(promo => (
        <CarouselItem key={promo.title} width="100%">
          {/* Same line count on every slide, so autoHeight never makes
              the mint block jump while rotating. */}
          <div className="flex flex-col">
            <Typography
              size="x-small"
              weight="bold"
              className="text-global-teal-teal-60">
              {promo.eyebrow}
            </Typography>
            <Typography size="2x-large" weight="bold" component="h2">
              {promo.title}
            </Typography>
            <Typography size="small" color="text-secondary">
              {promo.sub}
            </Typography>
          </div>
        </CarouselItem>
      ))}
    </Carousel>
  </section>
);
