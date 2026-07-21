/**
 * Cấu hình chạy. Chỉ đọc process.env ở đúng file này — phần còn lại
 * của server import `config`, không đụng vào process.env.
 */

export type VAppMode = 'mock' | 'real';

function required(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (value === undefined || value === '') {
    throw new Error(`Thiếu biến môi trường bắt buộc: ${name}`);
  }
  return value;
}

function int(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return fallback;
  const parsed = Number.parseInt(raw, 10);
  if (Number.isNaN(parsed)) {
    throw new Error(`${name} phải là số nguyên, nhận được: ${raw}`);
  }
  return parsed;
}

const nodeEnv = process.env.NODE_ENV ?? 'development';
const vappMode = (process.env.VAPP_MODE ?? 'mock') as VAppMode;

if (vappMode !== 'mock' && vappMode !== 'real') {
  throw new Error(`VAPP_MODE phải là 'mock' hoặc 'real', nhận được: ${vappMode}`);
}

// Chốt an toàn: mock cấp access token cho bất kỳ ai gọi. Nếu nó lọt lên
// production thì đó là một endpoint phát token vô điều kiện. Chết sớm còn hơn.
if (nodeEnv === 'production' && vappMode === 'mock') {
  throw new Error(
    'VAPP_MODE=mock không được phép chạy khi NODE_ENV=production. ' +
      'Mock cấp access token không cần xác thực thật.'
  );
}

export const config = {
  nodeEnv,
  /**
   * Tránh 3000–3999 (Simulator của v-miniapp-cli) và 8080–8999
   * (Mini App server). Cả hai dải này do CLI chiếm khi chạy `dev`.
   */
  port: int('PORT', 4000),
  host: process.env.HOST ?? '127.0.0.1',

  vapp: {
    mode: vappMode,
    /**
     * Đây là biến duy nhất phải đổi khi ráp API thật.
     * mock: http://localhost:3000/__vapp
     * real: https://api.v-app.vn  (xác nhận lại baseUrl với DevCenter)
     */
    baseUrl: required('VAPP_BASE_URL', 'http://127.0.0.1:4000/__vapp'),
    clientId: required('VAPP_CLIENT_ID', 'v-market-dev'),
    clientSecret: required('VAPP_CLIENT_SECRET', 'dev-secret'),
  },

  jwt: {
    secret: required('JWT_SECRET', 'dev-jwt-secret-doi-truoc-khi-deploy'),
    ttlSeconds: int('JWT_TTL_SECONDS', 60 * 60 * 12),
  },

  mock: {
    /** authCode thật rất ngắn hạn. Giữ ngắn để lộ lỗi sớm. */
    authCodeTtlSeconds: int('MOCK_AUTHCODE_TTL_SECONDS', 60),
    /** Tài liệu V-App: access token thường 1 giờ. */
    accessTokenTtlSeconds: int('MOCK_ACCESS_TOKEN_TTL_SECONDS', 3600),
  },
} as const;

export const isMock = config.vapp.mode === 'mock';
