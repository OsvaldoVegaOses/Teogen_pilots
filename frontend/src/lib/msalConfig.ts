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
