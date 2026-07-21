import type { FastifyInstance } from 'fastify';
import { config } from '../../config.js';
import { formatScopes, parseScopes } from '../types.js';
import type { VAppEnvelope, VAppScope } from '../types.js';
import {
  SEED_USERS,
  consumeAuthCode,
  consumeRefreshToken,
  findUser,
  issueAuthCode,
  issueTokens,
  lookupAccessToken,
  projectUserInfo,
} from './store.js';

/**
 * Bản mô phỏng V-App Open API, mount dưới /__vapp.
 *
 * Nguyên tắc: mock khắt khe hơn thật, không lỏng hơn. Chỗ nào tài liệu
 * không nói rõ thì chọn phía nghiêm — để lỗi lộ ra bây giờ, không phải
 * lúc ráp API thật.
 *
 * Mã lỗi 101xx lấy từ developer.v-app.vn/backend-api/open-api/error-codes.
 * Mã cho lỗi authCode chưa được tài liệu hoá; giá trị dưới đây là do ta
 * đặt, nên gateway KHÔNG được phụ thuộc vào con số cụ thể — chỉ dựa vào
 * `code !== 0`.
 */

const ERR = {
  MISSING_AUTHORIZATION: 10101,
  INVALID_AUTHORIZATION_FORMAT: 10102,
  TOKEN_CHECK_FAILED: 10106,
  TOKEN_REVOKED_OR_EXPIRED: 10107,
  INTERNAL: 10701,
  // Chưa có trong tài liệu chính thức — xem chú thích trên.
  INVALID_CLIENT: 10201,
  INVALID_AUTH_CODE: 10202,
  AUTH_CODE_EXPIRED: 10203,
  AUTH_CODE_ALREADY_USED: 10204,
  INVALID_REFRESH_TOKEN: 10205,
} as const;

function ok<T>(data: T): VAppEnvelope<T> {
  return { code: 0, message: 'Success', data };
}

function fail(code: number, message: string): VAppEnvelope<null> {
  return { code, message, data: null };
}

type ExchangeBody = {
  client_id?: string;
  client_secret?: string;
  auth_code?: string;
};

type RefreshBody = {
  client_id?: string;
  client_secret?: string;
  refresh_token?: string;
};

type SimulatorAuthCodeBody = {
  user_id?: string;
  scopes?: string | string[];
};

function clientIsValid(clientId?: string, clientSecret?: string): boolean {
  return (
    clientId === config.vapp.clientId && clientSecret === config.vapp.clientSecret
  );
}

export function registerMockVAppRoutes(app: FastifyInstance): void {
  // ---------------------------------------------------------------------
  // Open API — mô phỏng đúng hình dạng thật
  // ---------------------------------------------------------------------

  app.post<{ Body: ExchangeBody }>(
    '/__vapp/oauth2/token/exchange',
    async (request, reply) => {
      const { client_id, client_secret, auth_code } = request.body ?? {};

      if (!clientIsValid(client_id, client_secret)) {
        return reply
          .code(401)
          .send(fail(ERR.INVALID_CLIENT, 'client_id hoặc client_secret sai'));
      }
      if (!auth_code) {
        return reply
          .code(400)
          .send(fail(ERR.INVALID_AUTH_CODE, 'Thiếu auth_code'));
      }

      const result = consumeAuthCode(auth_code);
      if (!result.ok) {
        const mapping = {
          not_found: [ERR.INVALID_AUTH_CODE, 'auth_code không hợp lệ'],
          expired: [ERR.AUTH_CODE_EXPIRED, 'auth_code đã hết hạn'],
          already_used: [ERR.AUTH_CODE_ALREADY_USED, 'auth_code đã được dùng'],
        } as const;
        const [code, message] = mapping[result.reason];
        return reply.code(400).send(fail(code, message));
      }

      const { accessToken, refreshToken } = issueTokens(
        result.userId,
        result.scopes,
        config.mock.accessTokenTtlSeconds
      );

      return reply.send(
        ok({
          access_token: accessToken,
          refresh_token: refreshToken,
          token_type: 'Bearer' as const,
          expires_in: config.mock.accessTokenTtlSeconds,
          scope: formatScopes(result.scopes),
        })
      );
    }
  );

  app.post<{ Body: RefreshBody }>(
    '/__vapp/oauth2/token/refresh',
    async (request, reply) => {
      const { client_id, client_secret, refresh_token } = request.body ?? {};

      if (!clientIsValid(client_id, client_secret)) {
        return reply
          .code(401)
          .send(fail(ERR.INVALID_CLIENT, 'client_id hoặc client_secret sai'));
      }
      if (!refresh_token) {
        return reply
          .code(400)
          .send(fail(ERR.INVALID_REFRESH_TOKEN, 'Thiếu refresh_token'));
      }

      const record = consumeRefreshToken(refresh_token);
      if (!record) {
        return reply
          .code(400)
          .send(
            fail(ERR.INVALID_REFRESH_TOKEN, 'refresh_token không hợp lệ')
          );
      }

      const { accessToken, refreshToken } = issueTokens(
        record.userId,
        record.scopes,
        config.mock.accessTokenTtlSeconds
      );

      return reply.send(
        ok({
          access_token: accessToken,
          refresh_token: refreshToken,
          token_type: 'Bearer' as const,
          expires_in: config.mock.accessTokenTtlSeconds,
          scope: formatScopes(record.scopes),
        })
      );
    }
  );

  app.get('/__vapp/open/identity/v1/userinfo', async (request, reply) => {
    const header = request.headers.authorization;

    if (!header) {
      return reply
        .code(401)
        .send(fail(ERR.MISSING_AUTHORIZATION, 'Thiếu header Authorization'));
    }
    if (!header.startsWith('Bearer ')) {
      return reply
        .code(401)
        .send(
          fail(
            ERR.INVALID_AUTHORIZATION_FORMAT,
            'Authorization phải bắt đầu bằng "Bearer "'
          )
        );
    }

    const token = header.slice('Bearer '.length).trim();
    const lookup = lookupAccessToken(token);

    if (!lookup.ok) {
      const code =
        lookup.reason === 'expired'
          ? ERR.TOKEN_REVOKED_OR_EXPIRED
          : ERR.TOKEN_CHECK_FAILED;
      return reply
        .code(401)
        .send(fail(code, 'Access token không hợp lệ hoặc đã hết hạn'));
    }

    const user = findUser(lookup.userId);
    if (!user) {
      return reply.code(500).send(fail(ERR.INTERNAL, 'Không tìm thấy user'));
    }

    // Lọc theo scope — xem chú thích trong store.projectUserInfo.
    return reply.send(ok(projectUserInfo(user, lookup.scopes)));
  });

  // ---------------------------------------------------------------------
  // Điều khiển demo — KHÔNG tồn tại trên V-App thật.
  // Thay cho JSAPI getAuthCode, vì JSAPI cần appIdentifier đã đăng ký.
  // ---------------------------------------------------------------------

  app.get('/__vapp/simulator/users', async () => {
    return ok(
      SEED_USERS.map((u) => ({
        user_id: u.user_id,
        name: u.name,
        avatar_url: u.avatar_url,
      }))
    );
  });

  app.post<{ Body: SimulatorAuthCodeBody }>(
    '/__vapp/simulator/authcode',
    async (request, reply) => {
      const { user_id, scopes } = request.body ?? {};

      if (!user_id || !findUser(user_id)) {
        return reply
          .code(400)
          .send(fail(ERR.INVALID_AUTH_CODE, 'user_id không tồn tại'));
      }

      const parsed: VAppScope[] = parseScopes(scopes);
      const granted: VAppScope[] = parsed.length > 0 ? parsed : ['auth'];

      const authCode = issueAuthCode(
        user_id,
        granted,
        config.mock.authCodeTtlSeconds
      );

      // Hình dạng khớp với success callback của JSAPI getAuthCode.
      return reply.send(
        ok({
          authCode,
          authSuccessScopes: granted,
          expires_in: config.mock.authCodeTtlSeconds,
        })
      );
    }
  );
}
