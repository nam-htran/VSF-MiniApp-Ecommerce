import { randomUUID, randomBytes } from 'node:crypto';
import type { VAppScope, VAppUserInfoData } from '../types.js';

/**
 * Kho dữ liệu trong bộ nhớ cho bản mô phỏng V-App.
 *
 * Cố tình KHÔNG bền vững: đây là simulator, restart thì sạch là đúng.
 * Kho dữ liệu thật của V-Market nằm chỗ khác.
 */

/** Người dùng có sẵn trên "V-App". user_id là UUID, giống hệt API thật. */
export type MockVAppUser = {
  user_id: string;
  name: string;
  date_of_birth: string;
  gender: string;
  phone_number: string;
  email: string;
  avatar_url: string;
};

/**
 * user_id cố định để seed dữ liệu V-Market khớp được sau khi restart.
 * Đây là user của "V-App", chưa mang khái niệm buyer/seller —
 * vai trò là dữ liệu của V-Market, không phải của V-App.
 */
export const SEED_USERS: readonly MockVAppUser[] = [
  {
    user_id: '11111111-1111-4111-8111-111111111111',
    name: 'Nguyễn Thị Mua',
    date_of_birth: '1995-04-12',
    gender: 'female',
    phone_number: '+84901000001',
    email: 'buyer@example.com',
    avatar_url: 'https://placehold.co/128x128?text=Buyer',
  },
  {
    user_id: '22222222-2222-4222-8222-222222222222',
    name: 'Trần Văn Bán A',
    date_of_birth: '1990-08-03',
    gender: 'male',
    phone_number: '+84901000002',
    email: 'seller-a@example.com',
    avatar_url: 'https://placehold.co/128x128?text=A',
  },
  {
    user_id: '33333333-3333-4333-8333-333333333333',
    name: 'Lê Thị Bán B',
    date_of_birth: '1992-12-21',
    gender: 'female',
    phone_number: '+84901000003',
    email: 'seller-b@example.com',
    avatar_url: 'https://placehold.co/128x128?text=B',
  },
];

type AuthCodeRecord = {
  userId: string;
  scopes: VAppScope[];
  expiresAtMs: number;
  used: boolean;
};

type TokenRecord = {
  userId: string;
  scopes: VAppScope[];
  expiresAtMs: number;
};

type RefreshRecord = {
  userId: string;
  scopes: VAppScope[];
};

const authCodes = new Map<string, AuthCodeRecord>();
const accessTokens = new Map<string, TokenRecord>();
const refreshTokens = new Map<string, RefreshRecord>();

/** Token opaque: chuỗi ngẫu nhiên, không encode dữ liệu gì bên trong.
 *  Nếu mock encode user_id vào token, sẽ có người decode nó ở backend
 *  và code đó chết ngay khi ráp API thật. */
function opaque(prefix: string): string {
  return `${prefix}_${randomBytes(24).toString('hex')}`;
}

export function findUser(userId: string): MockVAppUser | undefined {
  return SEED_USERS.find((u) => u.user_id === userId);
}

export function issueAuthCode(
  userId: string,
  scopes: VAppScope[],
  ttlSeconds: number
): string {
  const code = `ac_${randomUUID()}`;
  authCodes.set(code, {
    userId,
    scopes,
    expiresAtMs: Date.now() + ttlSeconds * 1000,
    used: false,
  });
  return code;
}

export type ConsumeResult =
  | { ok: true; userId: string; scopes: VAppScope[] }
  | { ok: false; reason: 'not_found' | 'expired' | 'already_used' };

/** authCode dùng MỘT lần. Gọi lại phải hỏng — API thật cũng vậy. */
export function consumeAuthCode(code: string): ConsumeResult {
  const record = authCodes.get(code);
  if (!record) return { ok: false, reason: 'not_found' };
  if (record.used) return { ok: false, reason: 'already_used' };
  if (Date.now() > record.expiresAtMs) return { ok: false, reason: 'expired' };

  record.used = true;
  return { ok: true, userId: record.userId, scopes: record.scopes };
}

export function issueTokens(
  userId: string,
  scopes: VAppScope[],
  ttlSeconds: number
): { accessToken: string; refreshToken: string } {
  const accessToken = opaque('vat');
  const refreshToken = opaque('vrt');

  accessTokens.set(accessToken, {
    userId,
    scopes,
    expiresAtMs: Date.now() + ttlSeconds * 1000,
  });
  refreshTokens.set(refreshToken, { userId, scopes });

  return { accessToken, refreshToken };
}

export type TokenLookup =
  | { ok: true; userId: string; scopes: VAppScope[] }
  | { ok: false; reason: 'not_found' | 'expired' };

export function lookupAccessToken(token: string): TokenLookup {
  const record = accessTokens.get(token);
  if (!record) return { ok: false, reason: 'not_found' };
  if (Date.now() > record.expiresAtMs) {
    accessTokens.delete(token);
    return { ok: false, reason: 'expired' };
  }
  return { ok: true, userId: record.userId, scopes: record.scopes };
}

export function consumeRefreshToken(token: string): RefreshRecord | undefined {
  const record = refreshTokens.get(token);
  if (!record) return undefined;
  // Xoay vòng refresh token, giống khuyến nghị của tài liệu:
  // refresh thành công trả về CẢ access token mới VÀ refresh token mới.
  refreshTokens.delete(token);
  return record;
}

/**
 * Lọc thông tin user theo scope của token.
 *
 * Đây là phần dễ làm ẩu nhất và cũng quan trọng nhất: nếu mock trả đủ
 * mọi trường bất kể scope, backend sẽ quen có sẵn phone_number, rồi
 * hỏng ở checkout khi ráp thật. `auth` chỉ được trả user_id.
 */
export function projectUserInfo(
  user: MockVAppUser,
  scopes: readonly VAppScope[]
): VAppUserInfoData {
  const data: VAppUserInfoData = { user_id: user.user_id };

  if (scopes.includes('profile')) {
    data.name = user.name;
    data.date_of_birth = user.date_of_birth;
    data.gender = user.gender;
    data.avatar_url = user.avatar_url;
  }
  if (scopes.includes('phone')) {
    data.phone_number = user.phone_number;
  }
  if (scopes.includes('email')) {
    data.email = user.email;
  }

  return data;
}

/** Chỉ dùng trong test, để mỗi ca test bắt đầu từ trạng thái sạch. */
export function resetMockStore(): void {
  authCodes.clear();
  accessTokens.clear();
  refreshTokens.clear();
}
