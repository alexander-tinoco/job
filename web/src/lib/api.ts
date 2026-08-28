import type {
  ApplicationDetail,
  Decision,
  DecisionKind,
  Opening,
  RankedPage,
  SearchHit,
} from "./types";

const TOKEN_KEY = "screening.admin-token";

/**
 * The admin token lives in localStorage.
 *
 * This is a placeholder and a weak one: a single shared secret, no users, no
 * expiry, no rotation, and readable by any script on the page. It is acceptable
 * for a one-company-per-deployment MVP and is not acceptable before a real
 * client. See the README.
 */
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* Private browsing. The token simply will not persist. */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Nothing to clear. */
  }
}

export class Unauthorized extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { "X-Admin-Token": token } : {}),
      ...init?.headers,
    },
  });

  if (response.status === 401 || response.status === 503) {
    throw new Unauthorized("Invalid or missing admin token.");
  }
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body.slice(0, 300) || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export const api = {
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
