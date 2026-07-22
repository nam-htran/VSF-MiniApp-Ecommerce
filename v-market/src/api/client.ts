/**
 * The only place in the app that decides how a network call is made.
 *
 * Inside V-App there is no `fetch` and no `XMLHttpRequest` — the runtime is
 * an isolated JS environment and every request goes through the platform
 * bridge, HTTPS only. See docs/day3/platform-constraints.md §1.
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

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
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
