"use client";

import { MsalProvider } from "@azure/msal-react";
import { EventType, EventMessage, AuthenticationResult } from "@azure/msal-browser";
import { ensureMsalInitialized, getMsalInstance } from "@/lib/msalInstance";
import { ReactNode, useEffect, useRef, useState } from "react";

interface ProvidersProps {
    children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
    const [isInitialized, setIsInitialized] = useState(false);
    const initStarted = useRef(false);

    useEffect(() => {
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
    }, []);

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

    return (
        <MsalProvider instance={getMsalInstance()}>
            {children}
        </MsalProvider>
    );
}

