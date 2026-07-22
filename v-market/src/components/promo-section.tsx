import { Typography } from '@v-miniapp/ui-react';

/**
 * The promo header from the reference: mint block bleeding to the top
 * edge, teal eyebrow line, a large claim, and a white "see all" pill
 * sitting below V-App's ⋯ ✕ controls.
 *
 * The promo copy is a visual placeholder — vouchers are out of the plan,
 * so nothing in the backend enforces this claim yet. It lives in these
 * three strings and nowhere else.
 */
export const PromoSection = () => (
  <section
    className="flex flex-col gap-3 bg-global-teal-teal-10 px-4 pb-4"
    style={{
      // Text starts just below the status bar, in the empty space left of
      // V-App's ⋯ ✕ pill. The 44px fallback stands in for the Simulator's
      // fake status bar; a real device injects the true inset.
      paddingTop: 'calc(var(--safe-area-inset-top, 44px) + 8px)',
    }}>
    {/* No "see all" here — it belongs to the product section below, which
        also keeps it naturally clear of V-App's ⋯ ✕ pill. */}
    <div>
      <Typography
        size="x-small"
        weight="bold"
        className="text-global-teal-teal-60">
        Bắt đầu tiết kiệm với
      </Typography>
      <Typography size="2x-large" weight="bold" component="h2">
        Freeship + giảm 10%
      </Typography>
      <Typography size="small" color="text-secondary">
        Cho đơn từ 120.000 ₫ tại cửa hàng chọn lọc
      </Typography>
    </div>
  </section>
);
