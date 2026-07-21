import { config } from '../config.js';
import { VAppApiError, parseScopes } from './types.js';
import type {
  VAppEnvelope,
  VAppScope,
  VAppTokenData,
  VAppUserInfoData,
} from './types.js';

/**
 * Client gọi V-App Open API.
 *
 * CHỈ CÓ MỘT bản cài. Chạy với mock hay với API thật chỉ khác nhau ở
 * `VAPP_BASE_URL`. Không có `MockVAppGateway` song song — hai bản cài
 * song song là cái bẫy: bản mock dùng hàng ngày nên luôn đúng, bản real
 * không ai chạy nên luôn sai, và chỉ lộ ra đúng hôm cần ráp.
 *
 * Vì vậy code dưới đây đi qua HTTP thật kể cả khi mock nằm cùng process.
 */

export type VAppToken = {
  accessToken: string;
  refreshToken: string;
  expiresInSeconds: number;
  scopes: VAppScope[];
};

async function readEnvelope<T>(response: Response): Promise<T> {
  let body: VAppEnvelope<T> | undefined;

  try {
    body = (await response.json()) as VAppEnvelope<T>;
  } catch {
    throw new VAppApiError(
      -1,
      `Phản hồi không phải JSON (HTTP ${response.status})`,
      response.status
    );
  }

  // Open API bọc mọi thứ trong envelope: HTTP 200 vẫn có thể là lỗi.
  // Luôn xét `code`, đừng xét mỗi response.ok.
  if (!body || typeof body.code !== 'number') {
    throw new VAppApiError(
      -1,
      'Phản hồi thiếu trường "code"',
      response.status
    );
  }
  if (body.code !== 0) {
    throw new VAppApiError(body.code, body.message, response.status);
  }

  return body.data;
}

function url(path: string): string {
  return `${config.vapp.baseUrl.replace(/\/$/, '')}${path}`;
}

export async function exchangeAuthCode(authCode: string): Promise<VAppToken> {
  const response = await fetch(url('/oauth2/token/exchange'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: config.vapp.clientId,
      client_secret: config.vapp.clientSecret,
      auth_code: authCode,
    }),
  });

  const data = await readEnvelope<VAppTokenData>(response);

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresInSeconds: data.expires_in,
    scopes: parseScopes(data.scope),
  };
}

export async function refreshToken(token: string): Promise<VAppToken> {
  const response = await fetch(url('/oauth2/token/refresh'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: config.vapp.clientId,
      client_secret: config.vapp.clientSecret,
      refresh_token: token,
    }),
  });

  const data = await readEnvelope<VAppTokenData>(response);

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresInSeconds: data.expires_in,
    scopes: parseScopes(data.scope),
  };
}

export async function getUserInfo(
  accessToken: string
): Promise<VAppUserInfoData> {
  const response = await fetch(url('/open/identity/v1/userinfo'), {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
  });

  return readEnvelope<VAppUserInfoData>(response);
}
