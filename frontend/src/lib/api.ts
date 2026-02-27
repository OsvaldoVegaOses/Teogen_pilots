/** TheoGen Frontend - Deployment Trigger **/
import { loginRequest } from "./msalConfig";
import { ensureMsalInitialized } from "./msalInstance";
import { getGoogleToken } from "./googleAuth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

/**
 * Helper to get the access token silently.
 */
function isJwtExpired(token: string, skewSeconds = 60): boolean {
    try {
        const [, payloadBase64] = token.split(".");
        if (!payloadBase64) return true;

        const normalized = payloadBase64.replace(/-/g, "+").replace(/_/g, "/");
        const padded = normalized.padEnd(normalized.length + (4 - (normalized.length % 4)) % 4, "=");
        const payloadRaw = atob(padded);
        const payload = JSON.parse(payloadRaw) as { exp?: number };

        if (!payload.exp) return true;
        const now = Math.floor(Date.now() / 1000);
        return payload.exp <= now + skewSeconds;
    } catch {
        return true;
    }
}

async function getAccessToken(forceRefresh = false): Promise<string | null> {
    // Check for Google id_token first (Google-authenticated users have no MSAL account)
    if (!forceRefresh) {
        const googleToken = getGoogleToken();
        if (googleToken) return googleToken;
    }

    const instance = await ensureMsalInitialized();
    const accounts = instance.getAllAccounts();

    if (accounts.length === 0) {
        // No active account found
        return null;
    }

    const activeAccount = instance.getActiveAccount() || accounts[0];
    if (!instance.getActiveAccount()) {
        instance.setActiveAccount(activeAccount);
    }

    const request = {
        ...loginRequest,
        account: activeAccount,
        forceRefresh,
    };

    try {
        let response = await instance.acquireTokenSilent(request);
        if (isJwtExpired(response.idToken)) {
            response = await instance.acquireTokenSilent({ ...request, forceRefresh: true });
        }
        // Use idToken, NOT accessToken. With OIDC-only scopes (openid/profile/email),
        // accessToken is issued for Microsoft Graph (different signing keys & audience).
        // The backend validates tokens against our app's CLIENT_ID as audience,
        // which matches the idToken. See auth.py for the validation logic.
        return response.idToken;
    } catch (error) {
        console.warn("Silent token acquisition failed, user interaction needed", error);
        return null;
    }
}

/**
 * Authenticated API client.
 * Automatically injects the Bearer token into requests.
 */
export async function apiClient(endpoint: string, options: RequestInit = {}): Promise<Response> {
    let token: string | null = null;
    try {
        token = await getAccessToken();
    } catch (msalErr) {
        console.warn("getAccessToken() threw unexpectedly, proceeding without token:", msalErr);
    }

    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string>),
    };

    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    // Set JSON content-type by default unless body is FormData (which sets own boundary)
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    // Ensure endpoint has leading slash
    const path = endpoint.startsWith("/") ? endpoint : "/" + endpoint;
    const url = `${API_BASE_URL}${path}`;

    try {
        const response = await fetch(url, {
            ...options,
            headers,
            cache: options.cache ?? "no-store",
        });

        if (response.status === 401) {
            const cloned = response.clone();
            let detail = "";
            try {
                const payload = await cloned.json();
                detail = String(payload?.detail ?? "");
            } catch {
                // ignore non-JSON body
            }

            const shouldRetry = /expired|invalid or expired token|signature has expired/i.test(detail);
            if (shouldRetry) {
                const refreshedToken = await getAccessToken(true);
                if (refreshedToken) {
                    const retryHeaders: Record<string, string> = {
                        ...(options.headers as Record<string, string>),
                        Authorization: `Bearer ${refreshedToken}`,
                    };
                    if (!(options.body instanceof FormData) && !retryHeaders["Content-Type"]) {
                        retryHeaders["Content-Type"] = "application/json";
                    }

                    return await fetch(url, {
                        ...options,
                        headers: retryHeaders,
                        cache: options.cache ?? "no-store",
                    });
                }
            }

            console.error("Unauthorized request to API", detail || response.statusText);
        }

        return response;
    } catch (error) {
        console.error("API Request Failed:", error);
        throw error;
    }
}

/**
 * Public API client (no auth required).
 * Useful for landing features accessible before login.
 */
export async function publicApiClient(endpoint: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string>),
    };

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    const path = endpoint.startsWith("/") ? endpoint : "/" + endpoint;
    const url = `${API_BASE_URL}${path}`;

    try {
        return await fetch(url, {
            ...options,
            headers,
            cache: options.cache ?? "no-store",
        });
    } catch (error) {
        console.error("Public API Request Failed:", error);
        throw error;
    }
}
