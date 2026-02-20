/** TheoGen Frontend - Deployment Trigger **/
import { loginRequest } from "./msalConfig";
import { ensureMsalInitialized } from "./msalInstance";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

/**
 * Helper to get the access token silently.
 */
async function getAccessToken(): Promise<string | null> {
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
    };

    try {
        const response = await instance.acquireTokenSilent(request);
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
    const token = await getAccessToken();

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
        });

        if (response.status === 401) {
            console.error("Unauthorized request to API");
            // Could trigger a re-login flow here if needed
        }

        return response;
    } catch (error) {
        console.error("API Request Failed:", error);
        throw error;
    }
}
