/**
 * Google Identity Services token storage utilities.
 * Stores the Google JWT id_token in localStorage for cross-tab persistence.
 * Tokens expire after 1 hour (Google's default) and are validated on every read.
 */

const GOOGLE_TOKEN_KEY = "theogen_google_id_token";

function _isExpired(token: string, skewSeconds = 60): boolean {
    try {
        const [, payloadBase64] = token.split(".");
        if (!payloadBase64) return true;
        const normalized = payloadBase64.replace(/-/g, "+").replace(/_/g, "/");
        const padded = normalized.padEnd(
            normalized.length + (4 - (normalized.length % 4)) % 4,
            "="
        );
        const payload = JSON.parse(atob(padded)) as { exp?: number };
        if (!payload.exp) return true;
        return payload.exp <= Math.floor(Date.now() / 1000) + skewSeconds;
    } catch {
        return true;
    }
}

/** Returns the stored Google id_token if it exists and is not expired. */
export function getGoogleToken(): string | null {
    if (typeof window === "undefined") return null;
    const token = localStorage.getItem(GOOGLE_TOKEN_KEY);
    if (!token || _isExpired(token)) {
        if (token) localStorage.removeItem(GOOGLE_TOKEN_KEY);
        return null;
    }
    return token;
}

export function setGoogleToken(token: string): void {
    if (typeof window !== "undefined") {
        localStorage.setItem(GOOGLE_TOKEN_KEY, token);
    }
}

export function clearGoogleToken(): void {
    if (typeof window !== "undefined") {
        localStorage.removeItem(GOOGLE_TOKEN_KEY);
    }
}
