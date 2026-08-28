import type {
  ApplicationDetail,
  Comparison,
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
/** Throttled after repeated failures. Distinct so the form can say so. */
export class RateLimited extends Error {}

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
  if (response.status === 429) {
    throw new RateLimited("Too many attempts.");
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

  /** Mints a read-only link. The token is returned once and never again. */
  share: (openingId: string, days = 14) =>
    request<{ url_path: string; link: { id: string; expires_at: string } }>(
      `/api/v1/openings/${openingId}/share`,
      { method: "POST", body: JSON.stringify({ scope: "shortlist", days }) },
    ),

  ranked: (openingId: string, limit = 100) =>
    request<RankedPage>(
      `/api/v1/openings/${openingId}/applications?limit=${limit}`,
    ),

  /** Lines two or three candidates up and says where the gap comes from. */
  compare: (openingId: string, ids: string[]) =>
    request<Comparison>(
      `/api/v1/openings/${openingId}/compare?${ids.map((id) => `ids=${id}`).join("&")}`,
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
