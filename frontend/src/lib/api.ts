export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

/** Decodes the `sub` (student_id) claim out of the stored JWT without verifying its signature. */
export function getStudentId(token: string): string | null {
  try {
    const payload = token.split(".")[1];
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof json.sub === "string" ? json.sub : null;
  } catch {
    return null;
  }
}

export async function authFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
}

/** Clears the stored session. Call before redirecting to /login. */
export function logout() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("token");
}

/** Reads the stored token (if any) and decodes the student_id out of it. */
export function getCurrentStudentId(): string | null {
  const token = getToken();
  if (!token) return null;
  return getStudentId(token);
}
