/**
 * The only place in the app that decides how a network call is made.
 *
 * Inside V-App there is no `fetch` and no `XMLHttpRequest` — the runtime is
 * an isolated JS environment and every request goes through the platform
 * bridge, HTTPS only. See docs/phase1/day3/platform-constraints.md §1.
 */
import { apisAsync } from '@v-miniapp/apis';

const BASE = import.meta.env.VITE_API_BASE

/**
 * The bridge is only present inside V-App or its Simulator. Outside it —
 * a plain browser tab, a unit test — `window.vsf` is undefined and
 * `apisAsync` throws on property access rather than returning undefined.
 */
const hasBridge = () =>
  typeof window !== 'undefined' && Boolean((window as { vsf?: unknown }).vsf);

export class ApiError extends Error {
  // Declared, not constructor parameter properties: tsconfig sets
  // `erasableSyntaxOnly`, so the type layer cannot emit runtime fields.
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`Request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

type RequestInit = {
  method?: string;
  data?: unknown;
  headers?: Record<string, string>;
};

let warnedHttpFallback = false;

/**
 * How to get a fresh token when the server says 401. Registered from
 * lib/session-renew.ts rather than imported, so the transport stays
 * unaware of sessions and there is no import cycle
 * (client -> auth -> client).
 */
type Renewer = () => Promise<string | null>;
let renewSession: Renewer | null = null;
let renewing: Promise<string | null> | null = null;

export function setSessionRenewer(fn: Renewer): void {
  renewSession = fn;
}

/** One renewal at a time: a screen fires several calls at once and they
 *  all get 401 together — they should share one login, not race. */
const renewOnce = (): Promise<string | null> => {
  if (!renewing) {
    renewing = renewSession!().finally(() => {
      renewing = null;
    });
  }
  return renewing;
};

const authorized = (headers?: Record<string, string>) =>
  Object.keys(headers ?? {}).some(key => key.toLowerCase() === 'authorization');

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  try {
    return await send<T>(path, init);
  } catch (error) {
    // Only a 401 on a call that actually carried a token is worth
    // retrying. A 401 without one is the caller's bug, not an expiry.
    const expired =
      error instanceof ApiError &&
      error.status === 401 &&
      authorized(init.headers) &&
      renewSession !== null;
    if (!expired) throw error;

    const token = await renewOnce();
    if (!token) throw error;

    // Safe to replay: reads are idempotent, and POST /orders carries an
    // Idempotency-Key for exactly this reason — the retry returns the
    // order that already exists rather than buying twice.
    return send<T>(path, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
  }
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  // Absolute URLs pass through — the auth flow talks to the mock V-App,
  // which lives on its own base. Everything else goes to the backend.
  const url = path.startsWith('http') ? path : `${BASE}${path}`;
  const method = init.method ?? 'GET';

  // The bridge is HTTPS-only — the Simulator rejects a plain-http URL
  // client-side with `"url" has to be loaded over https` before the
  // request even leaves the page. So the bridge is used exactly when it
  // can work: bridge present AND an https target (device, staging).
  // In local dev the target is http://127.0.0.1, and the Simulator is a
  // real browser, so its own fetch works — with CORS enabled on server/.
  if (hasBridge() && url.startsWith('https://')) {
    const response = await apisAsync.request({
      url,
      method,
      headers: init.headers,
      data: init.data,
      dataType: 'JSON',
      timeout: 30000,
    });

    const status = response.status ?? 200;
    if (status >= 400) throw new ApiError(status, response.data);
    return response.data as T;
  }

  if (hasBridge() && !warnedHttpFallback) {
    warnedHttpFallback = true;
    // One loud line, not one per request: this is expected in the
    // Simulator with an http base, and fatal on a real device — there is
    // no fetch there. Moving to a device means an https VITE_API_BASE.
    console.warn(
      `[api] bridge refuses plain http — using browser fetch for ${BASE}. ` +
        'A real device needs an https VITE_API_BASE.'
    );
  }

  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...init.headers },
    body: init.data === undefined ? undefined : JSON.stringify(init.data),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
