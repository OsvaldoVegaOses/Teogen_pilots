"use client";

import { Configuration, LogLevel } from "@azure/msal-browser";

const getRedirectUri = (): string => {
    if (typeof window === "undefined") return "/login/";
    return window.location.origin + "/login/";
};

export const msalConfig: Configuration = {
    auth: {
        clientId: process.env.NEXT_PUBLIC_AZURE_AD_CLIENT_ID || "",
        authority: `https://login.microsoftonline.com/${process.env.NEXT_PUBLIC_AZURE_AD_TENANT_ID || "common"}`,
        redirectUri: getRedirectUri(),
        postLogoutRedirectUri: typeof window !== "undefined" ? window.location.origin + "/" : "/",
    },
    cache: {
        cacheLocation: "localStorage", // Use localStorage so auth persists across tabs/sessions
    },
    system: {
        loggerOptions: {
            logLevel: LogLevel.Info, // Temporarily increase log level for debugging
            loggerCallback: (level, message, containsPii) => {
                if (containsPii) return; // Don't log PII
                if (level === LogLevel.Error) {
                    console.error("[MSAL]", message);
                } else if (level === LogLevel.Warning) {
                    console.warn("[MSAL]", message);
                } else if (level === LogLevel.Info) {
                    console.info("[MSAL]", message);
                }
            },
        },
    },
};

export const loginRequest = {
    scopes: ["openid", "profile", "email"],
};

export const googleLoginRequest = {
    scopes: ["openid", "profile", "email"],
    // Must use the specific tenant (not 'common') so Azure AD knows which
    // External Identities Google federation to invoke
    authority: "https://login.microsoftonline.com/3e151d68-e5ed-4878-932d-251fe1b0eaf1",
    domainHint: "google.com",
};
