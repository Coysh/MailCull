import type { Sender, ScanStatus, AuthStatus, ActionPreview, ActionResult, Decision } from './types';

const BASE = '/api';

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

// Auth
export const getAuthStatus = () => req<AuthStatus>('/auth/status');
export const getAuthStartUrl = () => req<{ consent_url: string }>('/auth/start');
export const postDisconnect = () => req<unknown>('/auth/disconnect', { method: 'POST' });

// Scan
export const postStartScan = (since_days?: number) =>
  req<{ scan_id: number }>('/scan', { method: 'POST', body: JSON.stringify({ since_days: since_days ?? null }) });
export const getScanStatus = (id: number) => req<ScanStatus>(`/scan/${id}`);
export const getLatestScan = () => req<ScanStatus | null>('/scan/latest/status');

// Senders
export const getSenders = (params?: {
  sort?: string; category?: string; capability?: string; decision?: string;
}) => {
  const qs = new URLSearchParams();
  if (params?.sort) qs.set('sort', params.sort);
  if (params?.category) qs.set('category', params.category);
  if (params?.capability) qs.set('capability', params.capability);
  if (params?.decision) qs.set('decision', params.decision);
  const q = qs.toString();
  return req<Sender[]>(`/senders${q ? '?' + q : ''}`);
};
export const postClassify = () => req<{ classified: number; degraded: boolean }>('/senders/classify', { method: 'POST' });
export const postDecisions = (items: { sender_id: string; decision: Decision }[]) =>
  req<{ updated: number }>('/senders/decisions', { method: 'POST', body: JSON.stringify(items) });

// Actions
export const postPreview = (sender_ids: string[]) =>
  req<ActionPreview[]>('/actions/preview', { method: 'POST', body: JSON.stringify({ sender_ids }) });
export const postExecute = (sender_ids: string[]) =>
  req<ActionResult[]>('/actions/execute', { method: 'POST', body: JSON.stringify({ sender_ids, confirm: true }) });
export const getActionLog = () => req<unknown[]>('/actions/log');

// Ollama status
export const getHealth = () => req<{ status: string; dry_run: boolean; version: string }>('/health');

// Settings
export interface BackendSettings { ollama_base_url: string; ollama_model: string; dry_run: boolean; scan_since_days: number; }
export const getSettings = () => req<BackendSettings>('/settings');
export const patchSettings = (patch: Partial<Pick<BackendSettings, 'ollama_base_url' | 'ollama_model'>>) =>
  req<BackendSettings>('/settings', { method: 'PATCH', body: JSON.stringify(patch) });
