"use client";

import { MsalProvider } from "@azure/msal-react";
import { PublicClientApplication } from "@azure/msal-browser";
import { msalConfig } from "@/lib/msalConfig";
import { ReactNode, useEffect, useState } from "react";

interface ProvidersProps {
    children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
    const [msalInstance, setMsalInstance] = useState<PublicClientApplication | null>(null);

    useEffect(() => {
        const pca = new PublicClientApplication(msalConfig);
        // Initialize MSAL v3+
        pca.initialize().then(() => {
            setMsalInstance(pca);
        }).catch(e => {
            console.error("MSAL Initialization Failed:", e);
        });
    }, []);

    if (!msalInstance) {
        // Return null or a loading spinner while initializing
        return null;
    }

    return (
        <MsalProvider instance={msalInstance}>
            {children}
        </MsalProvider>
    );
}
