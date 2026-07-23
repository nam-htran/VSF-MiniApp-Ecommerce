import { apiRequest } from './client';

/**
 * The auth seam. Everything below authCode — token exchange, userinfo,
 * account creation, JWT — happens in server/ and is identical whether
 * the code came from the real platform or the mock.
 *
 * Where the authCode comes from is the ONLY swappable part:
 *  - real V-App: apisAsync.getAuthCode({ scopes }) — needs an app
 *    registered in DevCenter, which this project does not have;
 *  - dev: the mock's /simulator endpoints, which also stand in for
 *    picking/creating the V-App account itself.
 */
const VAPP = import.meta.env.VITE_VAPP_BASE ?? 'http://127.0.0.1:4001';

/** The mock wraps everything in the Open API envelope; code 0 = success. */
type Envelope<T> = { code: number; message: string; data: T };

async function unwrap<T>(promise: Promise<  Envelope<T>>): Promise<T> {
  const envelope = await promise;
  if (envelope.code !== 0) throw new Error(envelope.message);
  return envelope.data;
}

export type VappAccount = {
  user_id: string;
  name: string;
  avatar_url: string;
};

export function listVappAccounts() {
  return unwrap<VappAccount[]>(apiRequest(`${VAPP}/simulator/users`));
}

export function registerVappAccount(name: string) {
  return unwrap<VappAccount>(
    apiRequest(`${VAPP}/simulator/users`, { method: 'POST', data: { name } })
  );
}

function mintAuthCode(userId: string, scopes: string) {
  return unwrap<{ authCode: string }>(
    apiRequest(`${VAPP}/simulator/authcode`, {
      method: 'POST',
      data: { user_id: userId, scopes },
    })
  );
}

export type SessionUser = { id: string; role: string; name: string | null };

export type SessionResult =
  | { status: 'AUTHENTICATED'; token: string; user: SessionUser }
  | { status: 'CONSENT_REQUIRED'; requiredScopes: string[] };

function createSession(authCode: string) {
  return apiRequest<SessionResult>('/auth/session', {
    method: 'POST',
    data: { authCode },
  });
}

/**
 * Phase one of login-free-system: scope 'auth' only, no consent screen.
 * A known user comes back AUTHENTICATED; a new one, CONSENT_REQUIRED.
 */
export async function loginSilently(userId: string): Promise<SessionResult> {
  const { authCode } = await mintAuthCode(userId, 'auth');
  return createSession(authCode);
}

/**
 * Phase two, after the user agreed on the consent screen: scopes
 * 'profile phone', which is when V-Market learns a name and phone
 * number and creates the account.
 */
export async function loginWithConsent(userId: string): Promise<SessionResult> {
  const { authCode } = await mintAuthCode(userId, 'profile phone');
  return createSession(authCode);
}
