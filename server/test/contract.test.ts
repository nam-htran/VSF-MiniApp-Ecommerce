/**
 * CONTRACT TEST — bộ test này chạy được với CẢ hai:
 *
 *   VAPP_MODE=mock  pnpm test:contract    # hôm nay, với bản mô phỏng
 *   VAPP_MODE=real  pnpm test:contract    # ngày có credential thật
 *
 * Đây là thứ biến "hy vọng ráp được" thành "biết chắc". Ngày lấy được
 * client_id/client_secret, chạy đúng lệnh trên: xanh hết là ráp xong,
 * đỏ chỗ nào là biết chính xác chỗ đó lệch.
 *
 * Lưu ý về chế độ real: authCode phải do người dùng thật bấm đồng ý
 * trên máy thật, không lấy được bằng script. Nên khi chạy real, truyền
 * một authCode vừa lấy qua VAPP_TEST_AUTH_CODE. Vì authCode dùng một
 * lần, chế độ real chỉ chạy được ca đầu tiên — các ca còn lại tự bỏ qua.
 */

process.env.NODE_ENV = 'test';
process.env.VAPP_MODE ??= 'mock';
process.env.MOCK_AUTHCODE_TTL_SECONDS ??= '60';

const MOCK_PORT = 4987;
const IS_MOCK = process.env.VAPP_MODE === 'mock';

if (IS_MOCK) {
  process.env.VAPP_BASE_URL = `http://127.0.0.1:${MOCK_PORT}/__vapp`;
  process.env.VAPP_CLIENT_ID = 'contract-test-client';
  process.env.VAPP_CLIENT_SECRET = 'contract-test-secret';
}

import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { FastifyInstance } from 'fastify';

const { buildServer } = await import('../src/server.js');
const { exchangeAuthCode, getUserInfo, refreshToken } = await import(
  '../src/vapp/gateway.js'
);
const { VAppApiError } = await import('../src/vapp/types.js');
const { config } = await import('../src/config.js');

/** user_id của tài khoản seed "người mua" trong bản mô phỏng. */
const BUYER_ID = '11111111-1111-4111-8111-111111111111';

let app: FastifyInstance | undefined;

beforeAll(async () => {
  if (!IS_MOCK) return;
  app = buildServer();
  await app.listen({ port: MOCK_PORT, host: '127.0.0.1' });
});

afterAll(async () => {
  await app?.close();
});

/**
 * Lấy authCode để test.
 * - mock: gọi endpoint điều khiển demo (thay cho JSAPI getAuthCode)
 * - real: đọc từ env, do người dùng lấy tay
 */
async function getTestAuthCode(scopes: string): Promise<string | undefined> {
  if (!IS_MOCK) return process.env.VAPP_TEST_AUTH_CODE;

  const response = await fetch(`${config.vapp.baseUrl}/simulator/authcode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: BUYER_ID, scopes }),
  });
  const body = (await response.json()) as {
    code: number;
    data: { authCode: string };
  };
  expect(body.code).toBe(0);
  return body.data.authCode;
}

describe('V-App Open API — hợp đồng', () => {
  it('đổi authCode hợp lệ thì nhận được access token và user_id', async () => {
    const authCode = await getTestAuthCode('auth');
    if (!authCode) return; // real mode, không có VAPP_TEST_AUTH_CODE

    const token = await exchangeAuthCode(authCode);

    expect(token.accessToken).toBeTruthy();
    expect(token.expiresInSeconds).toBeGreaterThan(0);

    const info = await getUserInfo(token.accessToken);

    // user_id là UUID — đừng để ai lỡ parse nó thành số.
    expect(info.user_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    );
  });

  it.runIf(IS_MOCK)('authCode chỉ dùng được MỘT lần', async () => {
    const authCode = await getTestAuthCode('auth');
    if (!authCode) return;

    await exchangeAuthCode(authCode);

    await expect(exchangeAuthCode(authCode)).rejects.toBeInstanceOf(
      VAppApiError
    );
  });

  it.runIf(IS_MOCK)('authCode không tồn tại thì bị từ chối', async () => {
    await expect(exchangeAuthCode('ac_khong-ton-tai')).rejects.toBeInstanceOf(
      VAppApiError
    );
  });

  it.runIf(IS_MOCK)(
    'scope "auth" CHỈ trả user_id — không có tên, không có số điện thoại',
    async () => {
      const authCode = await getTestAuthCode('auth');
      if (!authCode) return;

      const token = await exchangeAuthCode(authCode);
      const info = await getUserInfo(token.accessToken);

      expect(info.user_id).toBeTruthy();
      // Đây là ca test đáng giá nhất trong file. Nếu mock trả đủ mọi
      // trường bất kể scope, backend sẽ quen có sẵn phone_number rồi
      // hỏng ở checkout đúng lúc ráp thật.
      expect(info.name).toBeUndefined();
      expect(info.phone_number).toBeUndefined();
      expect(info.email).toBeUndefined();
    }
  );

  it.runIf(IS_MOCK)(
    'scope "profile phone" mới trả tên và số điện thoại',
    async () => {
      const authCode = await getTestAuthCode('profile phone');
      if (!authCode) return;

      const token = await exchangeAuthCode(authCode);
      const info = await getUserInfo(token.accessToken);

      expect(info.name).toBeTruthy();
      expect(info.phone_number).toBeTruthy();
      // Không xin email thì không được có email.
      expect(info.email).toBeUndefined();
    }
  );

  it.runIf(IS_MOCK)('refresh token trả về cặp token mới', async () => {
    const authCode = await getTestAuthCode('auth');
    if (!authCode) return;

    const first = await exchangeAuthCode(authCode);
    const second = await refreshToken(first.refreshToken);

    expect(second.accessToken).not.toBe(first.accessToken);
    expect(second.refreshToken).not.toBe(first.refreshToken);

    // Token mới phải dùng được ngay.
    const info = await getUserInfo(second.accessToken);
    expect(info.user_id).toBe(BUYER_ID);
  });

  it.runIf(IS_MOCK)('access token sai thì bị từ chối', async () => {
    await expect(getUserInfo('vat_khong-hop-le')).rejects.toBeInstanceOf(
      VAppApiError
    );
  });

  it.runIf(IS_MOCK)(
    'access token là chuỗi opaque, không chứa user_id',
    async () => {
      const authCode = await getTestAuthCode('auth');
      if (!authCode) return;

      const token = await exchangeAuthCode(authCode);

      // Nếu mock nhét user_id vào token, sẽ có người decode nó ở backend
      // thay vì gọi userinfo — và code đó chết ngay khi ráp API thật.
      expect(token.accessToken).not.toContain(BUYER_ID);
    }
  );
});
