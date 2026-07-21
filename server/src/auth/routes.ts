import type { FastifyInstance } from 'fastify';
import { exchangeAuthCode, getUserInfo } from '../vapp/gateway.js';
import { VAppApiError } from '../vapp/types.js';
import { createUser, findByVAppUserId } from '../users/store.js';
import { issueSessionToken } from './jwt.js';

/**
 * Đăng nhập theo đúng luồng V-App khuyến nghị.
 * Nguồn: developer.v-app.vn/backend-api/resources/login-free-system
 *
 * Luồng có HAI giai đoạn, và đây là chi tiết đáng giữ đúng:
 *
 *   1. MiniApp gọi getAuthCode(['auth']) — im lặng, KHÔNG hiện consent.
 *   2. Backend đổi lấy user_id.
 *   3a. user đã tồn tại  → phát JWT, xong. Người dùng cũ không bao giờ
 *       phải bấm đồng ý lần nữa.
 *   3b. user chưa tồn tại → trả CONSENT_REQUIRED. MiniApp gọi getAuthCode
 *       lần hai với ['profile','phone','email'] để hiện consent, rồi gọi
 *       lại endpoint này.
 *
 * Nhờ vậy màn hình consent chỉ xuất hiện đúng một lần trong đời mỗi user.
 */

type SessionBody = {
  authCode?: string;
};

/** Scope cần xin ở giai đoạn hai. V-Market cần tên + SĐT để giao hàng. */
const PROFILE_SCOPES = ['profile', 'phone'] as const;

export function registerAuthRoutes(app: FastifyInstance): void {
  app.post<{ Body: SessionBody }>('/auth/session', async (request, reply) => {
    const authCode = request.body?.authCode;

    if (!authCode) {
      return reply
        .code(400)
        .send({ error: 'MISSING_AUTH_CODE', message: 'Thiếu authCode' });
    }

    let vappUserId: string;
    let profileName: string | null = null;
    let profilePhone: string | null = null;

    try {
      const token = await exchangeAuthCode(authCode);
      const info = await getUserInfo(token.accessToken);

      vappUserId = info.user_id;
      profileName = info.name ?? null;
      profilePhone = info.phone_number ?? null;
    } catch (error) {
      if (error instanceof VAppApiError) {
        request.log.warn(
          { code: error.code, httpStatus: error.httpStatus },
          'Đổi authCode thất bại'
        );
        return reply.code(401).send({
          error: 'VAPP_AUTH_FAILED',
          message: 'Không xác thực được với V-App',
        });
      }
      throw error;
    }

    const existing = findByVAppUserId(vappUserId);

    if (existing) {
      const token = await issueSessionToken(existing);
      return reply.send({
        status: 'AUTHENTICATED',
        token,
        user: {
          id: existing.id,
          role: existing.role,
          sellerId: existing.sellerId,
          name: existing.name,
        },
      });
    }

    // User mới. Nếu authCode chỉ có scope 'auth' thì ta mới biết user_id,
    // chưa có tên/SĐT — chưa đủ để tạo tài khoản. Yêu cầu MiniApp xin
    // consent rồi quay lại.
    if (profileName === null) {
      return reply.send({
        status: 'CONSENT_REQUIRED',
        requiredScopes: PROFILE_SCOPES,
      });
    }

    const created = createUser({
      vappUserId,
      name: profileName,
      phoneNumber: profilePhone,
    });
    const token = await issueSessionToken(created);

    return reply.send({
      status: 'AUTHENTICATED',
      token,
      user: {
        id: created.id,
        role: created.role,
        sellerId: created.sellerId,
        name: created.name,
      },
    });
  });
}
