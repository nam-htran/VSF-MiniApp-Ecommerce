import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Icon,
  Sheet,
  SheetBody,
  SheetFooter,
  SheetHeader,
  Skeleton,
  TextField,
  Toast,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import {
  deleteComment,
  listComments,
  postComment,
  type FeedComment,
} from '@/api/feed';
import { useSession } from '@/lib/auth';

type LoadState =
  | { status: 'loading'; items: FeedComment[]; hasMore: false }
  | { status: 'failed'; items: FeedComment[]; hasMore: false }
  | { status: 'ready'; items: FeedComment[]; hasMore: boolean };

const formatTime = (iso: string) =>
  new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

export const FeedCommentsSheet = ({
  productId,
  count,
  onCountChange,
  onClose,
}: {
  productId: string;
  count: number;
  onCountChange: (count: number) => void;
  onClose: () => void;
}) => {
  const navigate = useNavigate();
  const session = useSession();
  const [state, setState] = useState<LoadState>({
    status: 'loading',
    items: [],
    hasMore: false,
  });
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);

  const load = useCallback(() => {
    setState({ status: 'loading', items: [], hasMore: false });
    listComments(productId)
      .then(page => {
        setState({ status: 'ready', items: page.items, hasMore: page.hasMore });
        onCountChange(page.count);
      })
      .catch(() => setState({ status: 'failed', items: [], hasMore: false }));
  }, [onCountChange, productId]);

  useEffect(load, [load]);

  const loadMore = async () => {
    if (state.status !== 'ready') return;
    try {
      const page = await listComments(productId, 30, state.items.length);
      setState({
        status: 'ready',
        items: [...state.items, ...page.items],
        hasMore: page.hasMore,
      });
      onCountChange(page.count);
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không tải thêm được bình luận',
        position: 'bottom',
      });
    }
  };

  const send = async () => {
    const content = draft.trim();
    if (!content || posting) return;
    setPosting(true);
    try {
      const created = await postComment(productId, content);
      setState(current => ({
        status: 'ready',
        items: [created, ...current.items],
        hasMore: current.hasMore,
      }));
      setDraft('');
      onCountChange(count + 1);
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không gửi được bình luận',
        position: 'bottom',
      });
    } finally {
      setPosting(false);
    }
  };

  const remove = async (commentId: string) => {
    try {
      await deleteComment(commentId);
      setState(current => ({
        ...current,
        items: current.items.filter(comment => comment.id !== commentId),
      }));
      onCountChange(Math.max(0, count - 1));
    } catch {
      Toast.show({
        type: 'negative',
        message: 'Không xoá được bình luận',
        position: 'bottom',
      });
    }
  };

  return (
    <Sheet open onBackdropClick={posting ? undefined : onClose}>
      <SheetHeader title={`Bình luận${count > 0 ? ` (${count})` : ''}`} />
      <SheetBody>
        <div className="flex min-h-64 flex-col gap-4 pb-2">
          {state.status === 'loading' ? (
            [0, 1, 2].map(item => (
              <div key={item} className="flex gap-3">
                <Skeleton className="size-9 shrink-0 rounded-full" />
                <div className="flex flex-1 flex-col gap-2 pt-1">
                  <Skeleton className="h-3 w-28" />
                  <Skeleton className="h-3 w-4/5" />
                </div>
              </div>
            ))
          ) : state.status === 'failed' ? (
            <Alert
              type="negative"
              title="Không tải được bình luận"
              action={<Button onClick={load}>Thử lại</Button>}
            />
          ) : state.items.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 py-10 text-center">
              <Icon name="message-content" size={36} color="text-tertiary" />
              <Typography size="small" weight="semibold">
                Chưa có bình luận
              </Typography>
              <Typography size="x-small" color="text-secondary">
                Hãy là người đầu tiên trò chuyện về sản phẩm này.
              </Typography>
            </div>
          ) : (
            state.items.map(comment => (
              <div key={comment.id} className="flex items-start gap-3">
                <Avatar
                  size={36}
                  shape="circle"
                  label={comment.authorName.charAt(0).toUpperCase()}
                />
                <div className="min-w-0 flex-1 rounded-2xl bg-alias-layer-01 px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <Typography size="x-small" weight="semibold" className="truncate">
                        {comment.authorName}
                      </Typography>
                      <Typography size="2x-small" color="text-tertiary">
                        {formatTime(comment.createdAt)}
                      </Typography>
                    </div>
                    {comment.isMine && (
                      <Button
                        type="ghost"
                        theme="neutral"
                        shape="pill"
                        aria-label="Xoá bình luận"
                        onClick={() => remove(comment.id)}
                        className="!-mr-2 !-mt-1 !size-8 !p-0">
                        <Icon name="trash" size={16} color="text-tertiary" />
                      </Button>
                    )}
                  </div>
                  <Typography size="small" className="mt-1 whitespace-pre-wrap break-words">
                    {comment.content}
                  </Typography>
                </div>
              </div>
            ))
          )}

          {state.status === 'ready' && state.hasMore && (
            <Button type="ghost" theme="neutral" shape="pill" onClick={loadMore}>
              Xem thêm bình luận
            </Button>
          )}
        </div>
      </SheetBody>
      <SheetFooter>
        {session ? (
          <TextField
            value={draft}
            onChange={setDraft}
            maxLength={1000}
            shape="pill"
            placeholder="Viết bình luận…"
            disabled={posting}
            trailingIcon={{ name: 'paper-plane' }}
            onTrailingIconClick={send}
            onKeyDown={event => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void send();
              }
            }}
            className="w-full"
          />
        ) : (
          <Button
            type="solid"
            theme="brand"
            shape="pill"
            block
            onClick={() =>
              navigate('/login', {
                state: { loginTarget: { pathname: '/feed' } },
              })
            }>
            Đăng nhập để bình luận
          </Button>
        )}
      </SheetFooter>
    </Sheet>
  );
};
