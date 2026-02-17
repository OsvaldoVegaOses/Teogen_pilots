"use client";

import { Configuration, LogLevel } from "@azure/msal-browser";

export const msalConfig: Configuration = {
    auth: {
        clientId: process.env.NEXT_PUBLIC_AZURE_AD_CLIENT_ID || "",
        authority: `https://login.microsoftonline.com/${process.env.NEXT_PUBLIC_AZURE_AD_TENANT_ID || "common"}`,
        redirectUri: typeof window !== "undefined" ? window.location.origin + "/" : "/",
        postLogoutRedirectUri: typeof window !== "undefined" ? window.location.origin + "/" : "/",
    },
    cache: {
        cacheLocation: "sessionStorage",
    },
    system: {
        loggerOptions: {
            logLevel: LogLevel.Warning,
            loggerCallback: (level, message) => {
                if (level === LogLevel.Error) {
                    console.error("[MSAL]", message);
                }
            },
        },
    },
};

export const loginRequest = {
    scopes: ["openid", "profile", "email"],
};
