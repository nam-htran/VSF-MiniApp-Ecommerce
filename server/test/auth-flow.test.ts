/**
 * Test luồng đăng nhập của V-Market (không phải contract test).
 *
 * Kiểm hai điều mà tài liệu login-free-system quy định:
 *   1. User mới chỉ có scope 'auth' → phải yêu cầu consent, chưa tạo tài khoản.
 *   2. User đã tồn tại → đăng nhập im lặng, KHÔNG hỏi consent lần nữa.
 *
 * Và một điều thuộc về thiết kế của V-Market:
 *   3. role/sellerId do V-Market quyết định, không đến từ V-App.
 */

process.env.NODE_ENV = 'test';
process.env.VAPP_MODE = 'mock';

const PORT = 4988;
process.env.VAPP_BASE_URL = `http://127.0.0.1:${PORT}/__vapp`;
process.env.VAPP_CLIENT_ID = 'auth-flow-client';
process.env.VAPP_CLIENT_SECRET = 'auth-flow-secret';

import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { FastifyInstance } from 'fastify';

const { buildServer } = await import('../src/server.js');
const { resetUserStore } = await import('../src/users/store.js');
const { resetMockStore } = await import('../src/vapp/mock/store.js');
const { verifySessionToken } = await import('../src/auth/jwt.js');

const BUYER_ID = '11111111-1111-4111-8111-111111111111';
const SELLER_A_ID = '22222222-2222-4222-8222-222222222222';

let app: FastifyInstance;

beforeAll(async () => {
  app = buildServer();
  await app.listen({ port: PORT, host: '127.0.0.1' });
});

afterAll(async () => {
  await app.close();
});

beforeEach(() => {
  resetUserStore();
  resetMockStore();
});

async function authCodeFor(userId: string, scopes: string): Promise<string> {
  const response = await app.inject({
    method: 'POST',
    url: '/__vapp/simulator/authcode',
    payload: { user_id: userId, scopes },
  });
  return response.json().data.authCode;
}

async function postSession(authCode: string) {
  const response = await app.inject({
    method: 'POST',
    url: '/auth/session',
    payload: { authCode },
  });
  return response.json();
}

describe('POST /auth/session', () => {
  it('user mới với scope "auth" thì yêu cầu consent, chưa tạo tài khoản', async () => {
    const body = await postSession(await authCodeFor(BUYER_ID, 'auth'));

    expect(body.status).toBe('CONSENT_REQUIRED');
    expect(body.requiredScopes).toContain('profile');
    expect(body.token).toBeUndefined();
  });

  it('sau khi có consent thì tạo tài khoản và phát JWT', async () => {
    await postSession(await authCodeFor(BUYER_ID, 'auth'));

    const body = await postSession(
      await authCodeFor(BUYER_ID, 'profile phone')
    );

    expect(body.status).toBe('AUTHENTICATED');
    expect(body.token).toBeTruthy();
    expect(body.user.name).toBeTruthy();
  });

  it('user đã tồn tại thì đăng nhập im lặng, không hỏi consent lần nữa', async () => {
    await postSession(await authCodeFor(BUYER_ID, 'profile phone'));

    // Lần sau chỉ cần scope 'auth' — đây chính là điểm của silent login.
    const body = await postSession(await authCodeFor(BUYER_ID, 'auth'));

    expect(body.status).toBe('AUTHENTICATED');
    expect(body.token).toBeTruthy();
  });

  it('role và sellerId đến từ V-Market, không phải từ V-App', async () => {
    const buyer = await postSession(
      await authCodeFor(BUYER_ID, 'profile phone')
    );
    const seller = await postSession(
      await authCodeFor(SELLER_A_ID, 'profile phone')
    );

    expect(buyer.user.role).toBe('BUYER');
    expect(buyer.user.sellerId).toBeNull();

    expect(seller.user.role).toBe('SELLER');
    expect(seller.user.sellerId).toBe('seller-a');

    // Cùng thông tin đó phải nằm trong JWT để phân quyền ở các API sau.
    const claims = await verifySessionToken(seller.token);
    expect(claims.role).toBe('SELLER');
    expect(claims.sellerId).toBe('seller-a');
  });

  it('authCode sai thì trả 401, không tạo phiên', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/auth/session',
      payload: { authCode: 'ac_bia-dat' },
    });

    expect(response.statusCode).toBe(401);
    expect(response.json().token).toBeUndefined();
  });
});
