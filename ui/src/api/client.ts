/**
 * Typed HTTP client for the llm-review-2 backend.
 * Endpoints are already namespaced (/chat, /agent), so there is no base prefix;
 * in dev they are proxied to the backend on :8081 (see vite.config.ts).
 */
import type { AgentRole, ChatModelName, ChatResponse } from './types';

export class ApiError extends Error {}

async function readJsonOrText(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : response.text();
}

async function throwForResponse(response: Response): Promise<void> {
  if (response.ok) return;
  const payload = await readJsonOrText(response);
  const detail =
    typeof payload === 'string'
      ? payload
      : (payload as { detail?: unknown })?.detail;
  if (typeof detail === 'string') throw new ApiError(detail);
  if (detail && typeof detail === 'object') throw new ApiError(JSON.stringify(detail));
  throw new ApiError(`HTTP ${response.status} ${response.statusText}`);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  await throwForResponse(res);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  await throwForResponse(res);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Catalogs
// ---------------------------------------------------------------------------

export const listModels = () => get<ChatModelName[]>('/chat/models');
export const listRoles = () => get<AgentRole[]>('/agent/roles');

// ---------------------------------------------------------------------------
// Ping chat — single-turn LLM tester
// ---------------------------------------------------------------------------

export const pingChat = (message: string, model: string, temperature = 0.7) =>
  post<ChatResponse>('/chat/ping', { message, model, temperature });
