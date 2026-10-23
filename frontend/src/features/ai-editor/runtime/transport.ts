import { editorFileUrl, getEditorProviders, runEditorJob } from '../../../services/editorClient';

function findProvider(url: URL) {
  const match = getEditorProviders().find(provider => provider.hosts?.includes(url.hostname));
  if (match) return match.id;
  if (['localhost', '127.0.0.1'].includes(url.hostname)) {
    return ({ '11434': 'ollama', '1234': 'lmstudio', '8080': 'openai-compatible', '8188': 'comfyui', '7860': 'draw-things' } as Record<string, string>)[url.port];
  }
  return getEditorProviders().find(provider => provider.base_url && new URL(provider.base_url).origin === url.origin)?.id;
}

export async function encodeBinary(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  let result = '';
  for (let index = 0; index < bytes.length; index += 32768) result += String.fromCharCode(...bytes.subarray(index, index + 32768));
  return btoa(result);
}

/** Scoped transport; does not patch browser globals or intercept Rayflow's UI. */
export async function editorFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const source = input instanceof Request ? input.url : String(input);
  const location = typeof window === 'undefined' ? new URL('http://localhost') : window.location || new URL('http://localhost');
  let url = new URL(source, location.href);
  if (url.hostname === 'corsproxy.io') {
    // Upstream browser adapters wrapped provider calls in a public CORS proxy.
    // Route the original endpoint through our owned transport instead.
    url = new URL(decodeURIComponent(url.search.slice(1)), location.href);
    input = url.href;
  }
  if (['data:', 'blob:'].includes(url.protocol) || url.origin === location.origin) return globalThis.fetch(input, { credentials: 'include', ...init });
  const provider = findProvider(url);
  const cloud = ['api.dropboxapi.com', 'content.dropboxapi.com'].includes(url.hostname) ? 'dropbox'
    : ['www.googleapis.com', 'content.googleapis.com'].includes(url.hostname) ? 'google-drive' : undefined;
  if (!provider && !cloud) return globalThis.fetch(input, init);
  const request = input instanceof Request ? input : undefined;
  const method = (init.method || request?.method || 'GET').toUpperCase();
  const headers = Object.fromEntries(new Headers(init.headers || request?.headers).entries());
  let body: string | null = null;
  let body_base64: string | null = null;
  let form: Record<string, string>[] | undefined;
  if (typeof init.body === 'string') body = init.body;
  else if (init.body instanceof URLSearchParams) body = init.body.toString();
  else if (init.body instanceof Blob) body_base64 = await encodeBinary(await init.body.arrayBuffer());
  else if (init.body instanceof ArrayBuffer) body_base64 = await encodeBinary(init.body);
  else if (ArrayBuffer.isView(init.body)) body_base64 = await encodeBinary(new Uint8Array(init.body.buffer, init.body.byteOffset, init.body.byteLength).slice().buffer);
  else if (init.body instanceof FormData) {
    form = [];
    for (const [name, value] of init.body.entries()) form.push(typeof value === 'string' ? { name, value } : {
      name, filename: value.name, type: value.type, base64: await encodeBinary(await value.arrayBuffer()),
    });
  }
  else if (request && method !== 'GET') body = await request.text();
  const result = await runEditorJob(cloud ? 'cloud' : 'provider', { provider: cloud || provider, url: url.href, method, headers, body, body_base64, form }, init.signal || undefined);
  if (result.asset_path) return globalThis.fetch(editorFileUrl(result.asset_path), { credentials: 'include', signal: init.signal });
  const bytes = result.base64 ? Uint8Array.from(atob(result.base64), ch => ch.charCodeAt(0)) : result.text || '';
  return new Response([204, 304].includes(result.status) ? null : bytes, { status: result.status, headers: { ...result.headers, 'Content-Type': result.content_type } });
}
