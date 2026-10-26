const base = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');
export interface ProviderSettings {
  gemini_configured: boolean; gemini_model: string;
  openai_configured: boolean; anthropic_configured: boolean;
  agentrouter_configured: boolean; agentrouter_model: string; agentrouter_base_url: string;
  openrouter_configured: boolean; openrouter_model: string; pixabay_configured: boolean;
  ollama_host: string; ollama_model: string; ai_provider: string; editable: boolean;
}
export async function backendRequest<T>(path: string, init: RequestInit = {}, timeout = 20000): Promise<T> {
  const response = await fetch(`${base}${path}`, { credentials: 'include', ...init, signal: AbortSignal.timeout(timeout), headers: { 'Content-Type': 'application/json', ...init.headers } });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Backend request failed (HTTP ${response.status}).`);
  if (data === null) throw new Error('The backend returned an invalid response. Check the API URL.');
  return data;
}
export const getSettings = () => backendRequest<ProviderSettings>('/settings');
export const saveSettings = async (values: Record<string, string>) => {
  const saved = await backendRequest<ProviderSettings>('/settings', { method: 'PUT', body: JSON.stringify({ values }) });
  window.dispatchEvent(new Event('rayflow:director-settings'));
  return saved;
};
