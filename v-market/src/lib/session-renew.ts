/**
 * Getting a working token back without asking the user to log in again.
 *
 * There is no refresh token here, and there is not supposed to be. V-App's
 * login-free-system has no such thing: the way to renew is to call
 * getAuthCode(['auth']) again — silent for anyone who has already consented
 * — and exchange it for a fresh session. Storing a second long-lived
 * credential on the device would add risk and buy nothing.
 *
 * So renewal is just login, run again quietly. In dev the mock's
 * /simulator/authcode stands in for getAuthCode; the exchange after that is
 * byte-for-byte the real flow.
 *
 * Registered as a side effect from main.tsx.
 */
import { setSessionRenewer } from '@/api/client';
import { loginSilently } from '@/api/auth';
import { currentSession, signIn, signOut } from '@/lib/auth';

setSessionRenewer(async () => {
  const session = currentSession();
  if (!session) return null;

  try {
    const result = await loginSilently(session.vappUserId);
    if (result.status === 'AUTHENTICATED') {
      signIn({
        token: result.token,
        user: result.user,
        vappUserId: session.vappUserId,
      });
      return result.token;
    }
  } catch {
    // The mock or the backend is unreachable. Keep the session: the token
    // may well be fine and this is a network problem, and dropping someone
    // out of their cart because a server restarted is the worse mistake.
    return null;
  }

  // CONSENT_REQUIRED means the V-App account no longer has a V-Market
  // account behind it — the usual cause is the database being wiped and
  // re-seeded. The stored session points at a user id that is gone, so it
  // is dead weight. Clear it and let the route guard show the login screen.
  signOut();
  return null;
});
