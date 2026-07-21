import { SignJWT, jwtVerify } from 'jose';
import { config } from '../config.js';
import type { MarketUser } from '../users/store.js';

/**
 * Phiên đăng nhập của V-Market.
 *
 * Access token của V-App KHÔNG BAO GIỜ ra tới client — nó chỉ sống ở
 * backend. Client chỉ cầm JWT này.
 */

const secret = new TextEncoder().encode(config.jwt.secret);

export type SessionClaims = {
  sub: string;
  role: MarketUser['role'];
  sellerId: string | null;
};

export async function issueSessionToken(user: MarketUser): Promise<string> {
  return new SignJWT({ role: user.role, sellerId: user.sellerId })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(user.id)
    .setIssuedAt()
    .setExpirationTime(`${config.jwt.ttlSeconds}s`)
    .sign(secret);
}

export async function verifySessionToken(
  token: string
): Promise<SessionClaims> {
  const { payload } = await jwtVerify(token, secret);

  return {
    sub: String(payload.sub),
    role: payload.role as MarketUser['role'],
    sellerId: (payload.sellerId as string | null) ?? null,
  };
}
