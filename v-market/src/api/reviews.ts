import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

/**
 * Product reviews. Reading is public; writing needs a session and, on the
 * server, a paid order for the product — the client just shows the form
 * when eligibility says so.
 */
export type Review = {
  id: string;
  rating: number;
  comment: string | null;
  reviewerName: string;
  createdAt: string;
};

export type ReviewList = {
  items: Review[];
  average: number;
  count: number;
  hasMore: boolean;
};

export type Eligibility = { canReview: boolean; myReview: Review | null };

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

export const listReviews = (productId: string, limit = 20) =>
  apiRequest<ReviewList>(`/products/${productId}/reviews?limit=${limit}`);

export const postReview = (
  productId: string,
  body: { rating: number; comment?: string | null }
) =>
  apiRequest<Review>(`/products/${productId}/reviews`, {
    method: 'POST',
    data: body,
    headers: bearer(),
  });

export const reviewEligibility = (productId: string) =>
  apiRequest<Eligibility>(`/products/${productId}/reviews/eligibility`, {
    headers: bearer(),
  });
