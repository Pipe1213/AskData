const CLIENT_TOKEN_STORAGE_KEY = "askdata-client-token";

export function getClientToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const existing = window.localStorage.getItem(CLIENT_TOKEN_STORAGE_KEY)?.trim();
  if (existing) {
    return existing;
  }

  const token =
    typeof window.crypto?.randomUUID === "function"
      ? window.crypto.randomUUID()
      : `askdata-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(CLIENT_TOKEN_STORAGE_KEY, token);
  return token;
}

