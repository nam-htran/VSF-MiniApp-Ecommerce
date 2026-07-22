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

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const url = `${BASE}${path}`;
  const method = init.method ?? 'GET';

  if (hasBridge()) {
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

  // Fallback so the app still runs under plain `vite dev` and in tests.
  // Logged loudly on purpose: if this ever fires inside the Simulator it
  // means the bridge is missing, and code that works here would fail on a
  // real device where `fetch` does not exist.
  console.warn(`[api] no V-App bridge, falling back to fetch: ${method} ${url}`);

  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...init.headers },
    body: init.data === undefined ? undefined : JSON.stringify(init.data),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
