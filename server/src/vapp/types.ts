/**
 * Kiểu dữ liệu bám theo tài liệu V-App Open API.
 * Nguồn: developer.v-app.vn/backend-api/open-api/obtain-access-token
 *        developer.v-app.vn/backend-api/resources/user-profile
 *        developer.v-app.vn/backend-api/open-api/scopes
 *
 * Giữ đúng snake_case như API thật. Không đổi sang camelCase ở tầng này —
 * chỗ nào cần camelCase thì map ở ranh giới nghiệp vụ, để khi so với
 * tài liệu vẫn đọc thẳng được.
 */

/**
 * `auth` = đăng nhập im lặng, chỉ trả user_id, không hiện màn hình consent.
 *
 * Lưu ý: @v-miniapp/apis@1.0.20 khai báo scope chỉ gồm
 * 'profile' | 'phone' | 'email' — CHƯA có 'auth'. Tài liệu thì có.
 * SDK đang đi sau tài liệu; cần kiểm chứng lại khi có app đăng ký thật.
 */
export type VAppScope = 'auth' | 'profile' | 'phone' | 'email';

export const ALL_SCOPES: readonly VAppScope[] = [
  'auth',
  'profile',
  'phone',
  'email',
];

/** Mọi response của Open API đều bọc trong envelope này. code === 0 là thành công. */
export type VAppEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

export type VAppTokenData = {
  access_token: string;
  refresh_token: string;
  token_type: 'Bearer';
  expires_in: number;
  /** Chuỗi scope ngăn cách bằng khoảng trắng, ví dụ 'profile phone email'. */
  scope: string;
};

export type VAppUserInfoData = {
  /** Định danh ổn định của user trên V-App. Luôn có. */
  user_id: string;
  /** Các trường dưới đây phụ thuộc scope của token. */
  name?: string;
  date_of_birth?: string;
  gender?: string;
  phone_number?: string;
  email?: string;
  avatar_url?: string;
};

/** Lỗi từ Open API: HTTP có thể 200 nhưng code !== 0. */
export class VAppApiError extends Error {
  readonly code: number;
  readonly httpStatus: number;

  constructor(code: number, message: string, httpStatus: number) {
    super(`V-App API lỗi ${code}: ${message}`);
    this.name = 'VAppApiError';
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

export function parseScopes(raw: string | string[] | undefined): VAppScope[] {
  if (raw === undefined) return [];
  // Tài liệu có chỗ viết scopes: ['profile phone email'] (một chuỗi),
  // chỗ khác viết ['profile','phone','email']. Nhận cả hai.
  const parts = (Array.isArray(raw) ? raw : [raw])
    .flatMap((s) => s.split(/[\s,]+/))
    .filter((s) => s.length > 0);

  return parts.filter((s): s is VAppScope =>
    (ALL_SCOPES as readonly string[]).includes(s)
  );
}

export function formatScopes(scopes: readonly VAppScope[]): string {
  return scopes.join(' ');
}
