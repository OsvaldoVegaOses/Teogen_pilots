"use client";

import { MsalProvider } from "@azure/msal-react";
import { EventType, EventMessage, AuthenticationResult } from "@azure/msal-browser";
import { ensureMsalInitialized, getMsalInstance } from "@/lib/msalInstance";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { ReactNode, useEffect, useRef, useState } from "react";

interface ProvidersProps {
    children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
    const msalConfigured = Boolean(
        process.env.NEXT_PUBLIC_AZURE_AD_CLIENT_ID &&
        process.env.NEXT_PUBLIC_AZURE_AD_TENANT_ID
    );
    const [isInitialized, setIsInitialized] = useState(!msalConfigured);
    const initStarted = useRef(false);
    const isBrowser = typeof window !== "undefined";
    const currentPath = isBrowser ? window.location.pathname : "/";
    const isAuthArea =
        currentPath.startsWith("/dashboard") ||
        currentPath.startsWith("/login") ||
        currentPath.startsWith("/signup");

    useEffect(() => {
        if (!msalConfigured) {
            return;
        }

        if (initStarted.current) return;
        initStarted.current = true;

        const instance = getMsalInstance();

        // Use event callbacks to handle login results instead of calling handleRedirectPromise manually.
        // MsalProvider already calls handleRedirectPromise internally — calling it twice causes warnings.
        const callbackId = instance.addEventCallback((event: EventMessage) => {
            if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
                const result = event.payload as AuthenticationResult;
                console.log("[Providers] Login success, account:", result.account?.username);
                instance.setActiveAccount(result.account);
            } else if (event.eventType === EventType.ACQUIRE_TOKEN_FAILURE) {
                console.error("[Providers] Acquire token failure:", event.error);
            } else if (event.eventType === EventType.HANDLE_REDIRECT_END) {
                console.log("[Providers] handleRedirectPromise completed");
                // After redirect is handled, ensure an active account is set from cache
                const accounts = instance.getAllAccounts();
                if (accounts.length > 0 && !instance.getActiveAccount()) {
                    instance.setActiveAccount(accounts[0]);
                    console.log("[Providers] Set active account from cache:", accounts[0].username);
                }
            }
        });

        // Only initialize MSAL — do NOT call handleRedirectPromise here
        ensureMsalInitialized().then(() => {
            console.log("[Providers] MSAL initialized successfully");
            setIsInitialized(true);
        }).catch((e) => {
            console.error("[Providers] MSAL initialization failed:", e);
            setIsInitialized(true); // Still show UI so user can try again
        });

        return () => {
            if (callbackId) {
                instance.removeEventCallback(callbackId);
            }
        };
    }, [msalConfigured]);

    if (!isInitialized) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
                <div className="text-center space-y-4">
                    <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-lg bg-indigo-600 font-bold text-white text-xl animate-pulse">
                        T
                    </div>
                    <p className="text-zinc-600 dark:text-zinc-400 text-sm animate-pulse">
                        Cargando TheoGen...
                    </p>
                </div>
            </div>
        );
    }

    if (!msalConfigured) {
        if (isAuthArea) {
            return (
                <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-6">
                    <div className="max-w-xl rounded-2xl border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
                        <h2 className="text-lg font-bold text-red-700 dark:text-red-300 mb-2">
                            Configuración de autenticación incompleta
                        </h2>
                        <p className="text-sm text-red-700/90 dark:text-red-300/90">
                            Faltan variables de entorno públicas de MSAL en el frontend desplegado:
                            <span className="font-mono"> NEXT_PUBLIC_AZURE_AD_CLIENT_ID </span>
                            y/o
                            <span className="font-mono"> NEXT_PUBLIC_AZURE_AD_TENANT_ID</span>.
                        </p>
                    </div>
                </div>
            );
        }

        // Landing/public pages can render even without MSAL.
        return <>{children}</>;
    }

    return (
        <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ""}>
            <MsalProvider instance={getMsalInstance()}>
                {children}
            </MsalProvider>
        </GoogleOAuthProvider>
    );
}

