"use client";

import { MsalProvider } from "@azure/msal-react";
import { PublicClientApplication, EventType } from "@azure/msal-browser";
import { msalConfig } from "@/lib/msalConfig";
import { ReactNode, useEffect, useRef, useState } from "react";

interface ProvidersProps {
    children: ReactNode;
}

// Create a single MSAL instance (singleton)
let msalInstanceSingleton: PublicClientApplication | null = null;

function getMsalInstance(): PublicClientApplication {
    if (!msalInstanceSingleton) {
        msalInstanceSingleton = new PublicClientApplication(msalConfig);
    }
    return msalInstanceSingleton;
}

export function Providers({ children }: ProvidersProps) {
    const [isInitialized, setIsInitialized] = useState(false);
    const initStarted = useRef(false);

    useEffect(() => {
        if (initStarted.current) return;
        initStarted.current = true;

        const instance = getMsalInstance();

        // Add event callback for debugging
        const callbackId = instance.addEventCallback((event) => {
            if (event.eventType === EventType.LOGIN_SUCCESS) {
                console.log("[Providers] Login success event received");
            } else if (event.eventType === EventType.ACQUIRE_TOKEN_FAILURE) {
                console.error("[Providers] Acquire token failure event:", event.error);
            } else if (event.eventType === EventType.HANDLE_REDIRECT_START) {
                console.log("[Providers] handleRedirectPromise started");
            } else if (event.eventType === EventType.HANDLE_REDIRECT_END) {
                console.log("[Providers] handleRedirectPromise completed");
            }
        });

        instance.initialize().then(() => {
            console.log("[Providers] MSAL initialized successfully");

            // Handle redirect promise - this processes the response from Microsoft
            return instance.handleRedirectPromise();
        }).then((response) => {
            if (response) {
                console.log("[Providers] Redirect response received, account:", response.account?.username);
                // Set the account that just logged in as active
                instance.setActiveAccount(response.account);
            } else {
                console.log("[Providers] No redirect response (normal page load)");
                // Check if there's already an active account
                const accounts = instance.getAllAccounts();
                if (accounts.length > 0 && !instance.getActiveAccount()) {
                    instance.setActiveAccount(accounts[0]);
                    console.log("[Providers] Set active account from cache:", accounts[0].username);
                }
            }
            setIsInitialized(true);
        }).catch((e) => {
            console.error("[Providers] MSAL initialization or redirect handling failed:", e);
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

