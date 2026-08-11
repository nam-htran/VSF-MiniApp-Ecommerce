import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

export type ReactionType = 'LIKE' | 'LOVE' | 'HAHA' | 'WOW' | 'SAD';

export type ReactionState = {
  reactedByMe: boolean;
  reactionType: ReactionType | null;
  reactionCount: number;
};

export type FeedComment = {
  id: string;
  content: string;
  authorName: string;
  createdAt: string;
  isMine: boolean;
};

export type FeedCommentPage = {
  items: FeedComment[];
  count: number;
  hasMore: boolean;
};

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

export function setReaction(productId: string, reactionType: ReactionType = 'LOVE') {
  return apiRequest<ReactionState>(`/products/${productId}/reaction`, {
    method: 'PUT',
    data: { reactionType },
    headers: bearer(),
  });
}

export function removeReaction(productId: string) {
  return apiRequest<ReactionState>(`/products/${productId}/reaction`, {
    method: 'DELETE',
    headers: bearer(),
  });
}

export function listComments(productId: string, limit = 30, offset = 0) {
  return apiRequest<FeedCommentPage>(
    `/products/${productId}/comments?limit=${limit}&offset=${offset}`,
    { headers: bearer() }
  );
}

export function postComment(productId: string, content: string) {
  return apiRequest<FeedComment>(`/products/${productId}/comments`, {
    method: 'POST',
    data: { content },
    headers: bearer(),
  });
}

export function deleteComment(commentId: string) {
  return apiRequest<null>(`/comments/${commentId}`, {
    method: 'DELETE',
    headers: bearer(),
  });
}
