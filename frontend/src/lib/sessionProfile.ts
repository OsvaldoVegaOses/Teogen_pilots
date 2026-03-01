"use client";

import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";
import { clearGoogleToken, getGoogleToken } from "./googleAuth";

export const SESSION_PROFILE_STORAGE_KEY = "theogen_session_profile_v1";

export type SessionProfile = {
    email: string;
    provider: "microsoft" | "google" | "unknown";
    displayName: string;
    organization: string;
};

function parseJwtPayload(token: string): Record<string, unknown> | null {
    try {
        const [, payloadBase64] = token.split(".");
        if (!payloadBase64) return null;
        const normalized = payloadBase64.replace(/-/g, "+").replace(/_/g, "/");
        const padded = normalized.padEnd(normalized.length + (4 - (normalized.length % 4)) % 4, "=");
        const binary = atob(padded);
        const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
        const utf8 = new TextDecoder("utf-8").decode(bytes);
        return JSON.parse(utf8) as Record<string, unknown>;
    } catch {
        return null;
    }
}

export function getBaseSessionProfile(accounts: AccountInfo[]): SessionProfile {
    if (accounts.length > 0) {
        const account = accounts[0];
        return {
            email: account.username || "",
            provider: "microsoft",
            displayName: account.name || account.username || "Usuario TheoGen",
            organization: "",
        };
    }

    const googleToken = getGoogleToken();
    if (googleToken) {
        const payload = parseJwtPayload(googleToken);
        return {
            email: String(payload?.email || ""),
            provider: "google",
            displayName: String(payload?.name || payload?.email || "Usuario TheoGen"),
            organization: "",
        };
    }

    return {
        email: "",
        provider: "unknown",
        displayName: "Usuario TheoGen",
        organization: "",
    };
}

export function loadSessionProfile(baseProfile: SessionProfile): SessionProfile {
    if (typeof window === "undefined") return baseProfile;
    try {
        const raw = localStorage.getItem(SESSION_PROFILE_STORAGE_KEY);
        if (!raw) return baseProfile;
        const parsed = JSON.parse(raw) as Partial<SessionProfile>;
        return {
            ...baseProfile,
            displayName: parsed.displayName?.trim() || baseProfile.displayName,
            organization: parsed.organization?.trim() || "",
        };
    } catch {
        return baseProfile;
    }
}

export function saveSessionProfile(profile: Pick<SessionProfile, "displayName" | "organization">): void {
    if (typeof window === "undefined") return;
    localStorage.setItem(SESSION_PROFILE_STORAGE_KEY, JSON.stringify(profile));
}

export function clearSessionProfile(): void {
    if (typeof window === "undefined") return;
    localStorage.removeItem(SESSION_PROFILE_STORAGE_KEY);
}

export async function clearBrowserSession(instance: IPublicClientApplication): Promise<void> {
    if (typeof window === "undefined") return;

    clearGoogleToken();
    clearSessionProfile();

    const storageTargets = [window.localStorage, window.sessionStorage];
    for (const storage of storageTargets) {
        const keysToDelete: string[] = [];
        for (let i = 0; i < storage.length; i += 1) {
            const key = storage.key(i);
            if (!key) continue;
            if (
                key.startsWith("msal.") ||
                key.startsWith("theory_task_") ||
                key === "export_tasks" ||
                key === "theory_viewer_state_v1" ||
                key === "dashboard_ui_state_v1" ||
                key === "theogen_google_id_token" ||
                key === SESSION_PROFILE_STORAGE_KEY ||
                key === "theogen_highlight_fragment"
            ) {
                keysToDelete.push(key);
            }
        }
        keysToDelete.forEach((key) => storage.removeItem(key));
    }

    const account = instance.getActiveAccount() || instance.getAllAccounts()[0] || undefined;
    if (account) {
        await instance.logoutRedirect({
            account,
            postLogoutRedirectUri: window.location.origin + "/",
        });
        return;
    }

    window.location.replace("/");
}
