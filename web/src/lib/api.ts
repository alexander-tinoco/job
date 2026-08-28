import type {
  ApplicationDetail,
  Decision,
  DecisionKind,
  Opening,
  RankedPage,
  SearchHit,
} from "./types";

/**
 * The session is an HttpOnly cookie, so there is nothing for this file to store
 * or attach. That is the point: no script on the page can read the credential,
 * which is what `localStorage` could never offer. `credentials: "include"` is
 * all that is needed, and the panel is same-origin behind nginx anyway.
 */
export class Unauthorized extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (response.status === 401) {
    throw new Unauthorized("Your session has expired.");
  }
  if (!response.ok) {
    const body = await response.text();
    let detail = body.slice(0, 300);
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail ?? detail;
    } catch {
      /* Not JSON; the raw body is the best we have. */
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  last_login_at: string | null;
}

export const api = {
  login: (email: string, password: string) =>
    request<User>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),

  me: () => request<User>("/api/v1/auth/me"),

  /** Runs the synchronous evaluation for one candidate, at full price. */
  evaluateNow: (applicationId: string) =>
    request<unknown>(`/api/v1/applications/${applicationId}/evaluate`, {
      method: "POST",
    }),

  openings: () => request<Opening[]>("/api/v1/openings"),

  ranked: (openingId: string, limit = 100) =>
    request<RankedPage>(
      `/api/v1/openings/${openingId}/applications?limit=${limit}`,
    ),

  detail: (applicationId: string) =>
    request<ApplicationDetail>(`/api/v1/applications/${applicationId}`),

  search: (openingId: string, query: string) =>
    request<{ hits: SearchHit[] }>(
      `/api/v1/openings/${openingId}/search?q=${encodeURIComponent(query)}`,
    ),

  decide: (applicationId: string, kind: DecisionKind, reason: string, by: string) =>
    request<Decision>(`/api/v1/applications/${applicationId}/decision`, {
      method: "POST",
      body: JSON.stringify({ kind, reason, decided_by: by }),
    }),

  /** Served as an attachment by the API; never rendered inline. */
  resumeUrl: (applicationId: string) =>
    `/api/v1/applications/${applicationId}/resume`,
};
