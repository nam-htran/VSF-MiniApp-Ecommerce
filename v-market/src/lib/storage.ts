import { apisAsync } from '@v-miniapp/apis';

/**
 * Persistent key-value storage behind one seam.
 *
 * Inside V-App this is the storage JSAPI — the platform plans to drop
 * localStorage and cookies, so nothing else may be used there. Outside
 * (plain browser tab, tests) the bridge is absent and apisAsync throws on
 * property access, so localStorage stands in.
 *
 * Failures degrade to null/no-op on purpose: losing a cached cart must
 * never crash the screen that reads it.
 */
const hasBridge = () =>
  typeof window !== 'undefined' && Boolean((window as { vsf?: unknown }).vsf);

export async function loadJson<T>(key: string): Promise<T | null> {
  try {
    if (hasBridge()) {
      const result = await apisAsync.getStorage({ key });
      const data = result?.data;
      if (data === undefined || data === null || data === '') return null;
      return (typeof data === 'string' ? JSON.parse(data) : data) as T;
    }
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export async function saveJson(key: string, value: unknown): Promise<void> {
  try {
    if (hasBridge()) {
      await apisAsync.setStorage({ key, data: value as Record<string, unknown> });
      return;
    }
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Persistence is best-effort; the in-memory state stays correct.
  }
}
