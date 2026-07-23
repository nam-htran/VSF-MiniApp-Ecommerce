import { currentToken } from '@/lib/auth';

/**
 * Image upload. Multipart, so it can't go through the JSON transport in
 * client.ts — a direct fetch here. In the Simulator that's a browser fetch
 * to the dev server; on a real device this seam would be the uploadFile
 * JSAPI instead. Returns the absolute URL the server serves the image at.
 */
const BASE = import.meta.env.VITE_API_BASE;

export async function uploadImage(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file);
  const token = currentToken();

  const response = await fetch(`${BASE}/uploads`, {
    method: 'POST',
    body: form,
    // No Content-Type: the browser sets the multipart boundary itself.
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? 'Tải ảnh thất bại');
  }
  return (await response.json()).url as string;
}
