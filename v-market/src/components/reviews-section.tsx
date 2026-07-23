import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Icon,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  TextField,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import {
  listReviews,
  postReview,
  reviewEligibility,
  type Eligibility,
  type Review,
  type ReviewList,
} from '@/api/reviews';
import { useSession } from '@/lib/auth';

/** Five stars, filled to `value`. Read-only. */
export const Stars = ({ value, size = 14 }: { value: number; size?: number }) => (
  <span className="flex items-center gap-0.5">
    {[1, 2, 3, 4, 5].map(i => (
      <Icon
        key={i}
        name="star"
        type={i <= Math.round(value) ? 'fill' : 'outline'}
        size={size}
        className={
          i <= Math.round(value)
            ? 'text-global-amber-amber-50'
            : 'text-alias-icon-tertiary'
        }
      />
    ))}
  </span>
);

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });

/**
 * The reviews block on the product page: the average and count, the list,
 * and — only for a buyer who paid for this product — a form to leave or
 * edit their own rating. Eligibility is asked of the server, so the form
 * never appears where it would be rejected anyway.
 */
export const ReviewsSection = ({ productId }: { productId: string }) => {
  const session = useSession();
  const [data, setData] = useState<ReviewList | null>(null);
  const [elig, setElig] = useState<Eligibility | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(() => {
    listReviews(productId, 20)
      .then(setData)
      .catch(() => setData({ items: [], average: 0, count: 0, hasMore: false }));
    if (session) {
      reviewEligibility(productId)
        .then(setElig)
        .catch(() => setElig(null));
    } else {
      setElig(null);
    }
  }, [productId, session]);

  useEffect(load, [load]);

  return (
    <div className="mx-3 flex flex-col gap-3 rounded-2xl bg-alias-background p-3.5 shadow-sm">
      <div className="flex items-center justify-between">
        <Typography size="base" weight="bold">
          Đánh giá
        </Typography>
        {elig?.canReview && (
          <button type="button" onClick={() => setFormOpen(true)}>
            <Typography size="x-small" className="text-brand">
              {elig.myReview ? 'Sửa đánh giá' : 'Viết đánh giá'}
            </Typography>
          </button>
        )}
      </div>

      {data && data.count > 0 ? (
        <div className="flex items-center gap-2">
          <Typography size="2x-large" weight="bold">
            {data.average.toFixed(1)}
          </Typography>
          <div className="flex flex-col">
            <Stars value={data.average} size={16} />
            <Typography size="2x-small" color="text-tertiary">
              {data.count} đánh giá
            </Typography>
          </div>
        </div>
      ) : (
        <Typography size="small" color="text-secondary">
          Chưa có đánh giá nào.
        </Typography>
      )}

      {data?.items.map(review => (
        <ReviewRow key={review.id} review={review} />
      ))}

      {formOpen && (
        <ReviewForm
          productId={productId}
          initial={elig?.myReview ?? null}
          onClose={() => setFormOpen(false)}
          onSaved={() => {
            setFormOpen(false);
            load();
          }}
        />
      )}
    </div>
  );
};

const ReviewRow = ({ review }: { review: Review }) => (
  <div className="flex flex-col gap-1 border-t border-alias-border-subtle-01 pt-2">
    <div className="flex items-center justify-between gap-2">
      <Typography size="small" weight="semibold" className="truncate">
        {review.reviewerName}
      </Typography>
      <Typography size="2x-small" color="text-tertiary" className="shrink-0">
        {formatDate(review.createdAt)}
      </Typography>
    </div>
    <Stars value={review.rating} />
    {review.comment && (
      <Typography size="small" color="text-secondary" className="whitespace-pre-line">
        {review.comment}
      </Typography>
    )}
  </div>
);

const ReviewForm = ({
  productId,
  initial,
  onClose,
  onSaved,
}: {
  productId: string;
  initial: Review | null;
  onClose: () => void;
  onSaved: () => void;
}) => {
  const [rating, setRating] = useState(initial?.rating ?? 5);
  const [comment, setComment] = useState(initial?.comment ?? '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await postReview(productId, {
        rating,
        comment: comment.trim() || null,
      });
      Toast.show({
        type: 'positive',
        message: 'Cảm ơn đánh giá của bạn',
        position: 'bottom',
      });
      onSaved();
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không gửi được đánh giá',
        position: 'bottom',
      });
      setSaving(false);
    }
  };

  return (
    <Sheet open onBackdropClick={saving ? undefined : onClose}>
      <SheetHeader title="Đánh giá sản phẩm" />
      <SheetBody>
        <div className="flex flex-col items-center gap-3 pb-2">
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map(i => (
              <button
                key={i}
                type="button"
                aria-label={`${i} sao`}
                onClick={() => setRating(i)}>
                <Icon
                  name="star"
                  type={i <= rating ? 'fill' : 'outline'}
                  size={32}
                  className={
                    i <= rating
                      ? 'text-global-amber-amber-50'
                      : 'text-alias-icon-tertiary'
                  }
                />
              </button>
            ))}
          </div>
          <TextField
            value={comment}
            onChange={setComment}
            placeholder="Chia sẻ cảm nhận của bạn (không bắt buộc)"
            className="w-full"
          />
        </div>
      </SheetBody>
      <SheetFooter>
        <div className="flex w-full gap-2">
          <Button type="outline" theme="neutral" block onClick={onClose}>
            Huỷ
          </Button>
          <Button type="solid" theme="brand" block loading={saving} onClick={save}>
            Gửi đánh giá
          </Button>
        </div>
      </SheetFooter>
    </Sheet>
  );
};
