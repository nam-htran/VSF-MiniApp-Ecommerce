import { useCallback, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Icon,
  Image,
  PullToRefresh,
  Skeleton,
  Toast,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { removeReaction, setReaction } from '@/api/feed';
import { listProducts, PRODUCT_PAGE } from '@/api/products';
import { FeedCommentsSheet } from '@/components/feed-comments-sheet';
import { useSession } from '@/lib/auth';
import { formatVnd } from '@/lib/format';
import { usePagedProducts } from '@/lib/paged-feed';
import type { ProductCardData } from '@/lib/product-card';

const formatCount = (value: number) =>
  value >= 1000 ? `${(value / 1000).toFixed(1).replace('.', ',')}K` : String(value);

const FeedPage = () => {
  const page = useCallback(
    (offset: number) => listProducts(PRODUCT_PAGE, offset),
    []
  );
  const { feed, load, refresh, sentinel } = usePagedProducts(page);

  const products = feed.status === 'ready' ? feed.products : [];
  const trending = products.filter(
    (product, index, all) =>
      Boolean(product.shopId) &&
      all.findIndex(item => item.shopId === product.shopId) === index
  );

  const onRefresh = () =>
    refresh().catch(() =>
      Toast.show({
        type: 'negative',
        message: 'Không làm mới được Feed, thử lại sau',
        position: 'bottom',
      })
    );

  return (
    <PullToRefresh
      onRefresh={onRefresh}
      pullingText="Kéo xuống để làm mới"
      canReleaseText="Thả ra để làm mới"
      refreshingText="Đang làm mới…"
      completeText="Đã cập nhật">
      <div className="min-h-full bg-alias-layer-01 pb-4">
        <section
          className="flex flex-col gap-3 border-b border-alias-border-subtle-01 bg-alias-background px-4 pb-3"
          style={{ paddingTop: 'calc(var(--safe-area-inset-top, 44px) + 12px)' }}>
          <Typography size="2x-large" weight="bold" component="h1">
            Xu hướng
          </Typography>
          <div className="-mx-4 flex gap-4 overflow-x-auto px-4 py-2">
            {feed.status === 'loading'
              ? [0, 1, 2, 3, 4].map(item => (
                  <Skeleton key={item} className="size-16 shrink-0 rounded-full" />
                ))
              : trending.map(product => (
                  <TrendingShop key={product.shopId} product={product} />
                ))}
          </div>
        </section>

        {feed.status === 'failed' ? (
          <div className="p-4">
            <Alert
              type="negative"
              title="Không tải được Feed"
              message={feed.message}
              action={
                <Button shape="pill" onClick={load}>
                  Thử lại
                </Button>
              }
            />
          </div>
        ) : feed.status === 'loading' ? (
          <FeedSkeleton />
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-8 py-16 text-center">
            <Icon name="newspaper" size={40} color="text-tertiary" />
            <Typography size="large" weight="semibold">
              Feed chưa có bài viết
            </Typography>
            <Typography size="small" color="text-secondary">
              Sản phẩm mới từ các cửa hàng sẽ xuất hiện tại đây.
            </Typography>
          </div>
        ) : (
          <div className="flex flex-col gap-2 pt-2">
            {products.map(product => (
              <FeedPost key={product.id} product={product} />
            ))}
            {feed.hasMore && (
              <div ref={sentinel} className="flex justify-center py-6">
                <Typography size="small" color="text-secondary">
                  Đang tải thêm…
                </Typography>
              </div>
            )}
          </div>
        )}
      </div>
    </PullToRefresh>
  );
};

const TrendingShop = ({ product }: { product: ProductCardData }) => {
  const navigate = useNavigate();
  const shopName = product.shopName ?? 'Cửa hàng';

  return (
    <Button
      type="ghost"
      theme="neutral"
      onClick={() =>
        product.shopId && navigate('/shop', { params: { id: product.shopId } })
      }
      className="!h-auto !min-h-0 !max-h-none !shrink-0 !flex-col !gap-1 !rounded-xl !p-1">
      <Avatar
        src={product.image}
        size={62}
        shape="circle"
        border
        label={shopName.charAt(0).toUpperCase()}
      />
      <Typography size="2x-small" className="w-16 truncate text-center">
        {shopName}
      </Typography>
    </Button>
  );
};

const FeedPost = ({ product }: { product: ProductCardData }) => {
  const navigate = useNavigate();
  const session = useSession();
  const [expanded, setExpanded] = useState(false);
  const [liked, setLiked] = useState(product.reactedByMe ?? false);
  const [reactionCount, setReactionCount] = useState(product.reactionCount ?? 0);
  const [commentCount, setCommentCount] = useState(product.commentCount ?? 0);
  const [reactionBusy, setReactionBusy] = useState(false);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const shopName = product.shopName ?? 'V-Market Shop';
  const canExpand = (product.description?.length ?? 0) > 130;

  const openProduct = () =>
    navigate('/product', {
      params: { id: product.id },
      state: { product },
    });

  const toggleReaction = async () => {
    if (!session) {
      navigate('/login', {
        state: { loginTarget: { pathname: '/feed' } },
      });
      return;
    }
    if (reactionBusy) return;

    const previousLiked = liked;
    const previousCount = reactionCount;
    const nextLiked = !liked;
    setLiked(nextLiked);
    setReactionCount(Math.max(0, previousCount + (nextLiked ? 1 : -1)));
    setReactionBusy(true);
    try {
      const saved = nextLiked
        ? await setReaction(product.id, 'LOVE')
        : await removeReaction(product.id);
      setLiked(saved.reactedByMe);
      setReactionCount(saved.reactionCount);
    } catch {
      setLiked(previousLiked);
      setReactionCount(previousCount);
      Toast.show({
        type: 'negative',
        message: 'Không cập nhật được cảm xúc',
        position: 'bottom',
      });
    } finally {
      setReactionBusy(false);
    }
  };

  return (
    <article className="bg-alias-background py-3">
      <div className="flex items-center gap-3 px-4">
        <Avatar
          src={product.image}
          size={40}
          shape="circle"
          border
          label={shopName.charAt(0).toUpperCase()}
        />
        <div className="min-w-0 flex-1">
          <Typography size="small" weight="semibold" className="truncate">
            {shopName}
          </Typography>
          <Typography size="2x-small" color="text-tertiary" className="truncate">
            {product.shopProvince ?? 'Gợi ý cho bạn'}
          </Typography>
        </div>
        <Button
          type="ghost"
          theme="neutral"
          shape="pill"
          aria-label="Tuỳ chọn bài viết"
          onClick={() => Toast.show({ message: 'Tuỳ chọn bài viết' })}
          className="!size-9 !p-0">
          <Icon name="dots" size={20} color="text-tertiary" />
        </Button>
      </div>

      <div className="px-4 pb-3 pt-2">
        <Typography size="small" weight="semibold">
          {product.name}
        </Typography>
        {product.description && (
          <Typography
            size="x-small"
            color="text-secondary"
            className={`mt-1 ${expanded ? '' : 'line-clamp-3'}`}>
            {product.description}
          </Typography>
        )}
        {canExpand && (
          <Button
            type="ghost"
            theme="neutral"
            aria-expanded={expanded}
            onClick={() => setExpanded(value => !value)}
            className="mt-1 !h-auto !min-h-0 !max-h-none !justify-start !rounded-none !p-0">
            <Typography size="x-small" weight="semibold" color="text-secondary">
              {expanded ? 'Thu gọn' : 'Xem thêm'}
            </Typography>
          </Button>
        )}
      </div>

      <Button
        type="ghost"
        theme="neutral"
        block
        aria-label={`Xem ${product.name}`}
        onClick={openProduct}
        className="!block !h-auto !min-h-0 !max-h-none !rounded-none !p-0">
        <Image
          src={product.image}
          alt={product.name}
          fit="cover"
          className="aspect-[16/10] w-full"
          fallback={
            <div className="flex aspect-[16/10] w-full items-center justify-center bg-alias-layer-01">
              <Icon name="image" size={44} color="text-tertiary" />
            </div>
          }
        />
      </Button>

      <div className="flex items-center gap-1 px-3 py-2">
        <Button
          type="ghost"
          theme="neutral"
          shape="pill"
          onClick={toggleReaction}
          disabled={reactionBusy}
          leadingIcon={
            <Icon
              name="heart"
              type={liked ? 'fill' : 'outline'}
              size={21}
              className={liked ? 'text-brand' : ''}
            />
          }
          className="!px-2">
          {formatCount(reactionCount)}
        </Button>
        <Button
          type="ghost"
          theme="neutral"
          shape="pill"
          onClick={() => setCommentsOpen(true)}
          leadingIcon={{ name: 'message-content' }}
          className="!px-2">
          {formatCount(commentCount)}
        </Button>
      </div>

      <div className="mx-4 flex items-center gap-3 rounded-xl bg-alias-layer-01 p-2.5">
        <div className="min-w-0 flex-1">
          <Typography size="x-small" weight="semibold" className="truncate">
            {product.name}
          </Typography>
          <Typography size="small" weight="bold" className="text-brand">
            {formatVnd(product.effectivePrice ?? product.price)}
          </Typography>
        </div>
        <Button type="solid" theme="brand" shape="pill" onClick={openProduct}>
          Xem sản phẩm
        </Button>
      </div>

      {commentsOpen && (
        <FeedCommentsSheet
          productId={product.id}
          count={commentCount}
          onCountChange={setCommentCount}
          onClose={() => setCommentsOpen(false)}
        />
      )}
    </article>
  );
};

const FeedSkeleton = () => (
  <div className="flex flex-col gap-2 pt-2">
    {[0, 1].map(item => (
      <div key={item} className="flex flex-col gap-3 bg-alias-background py-3">
        <div className="flex items-center gap-3 px-4">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-2.5 w-20" />
          </div>
        </div>
        <div className="px-4">
          <Skeleton className="h-3 w-3/4" />
        </div>
        <Skeleton className="aspect-[16/10] w-full rounded-none" />
      </div>
    ))}
  </div>
);

export default FeedPage;
