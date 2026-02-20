import { PublicClientApplication } from "@azure/msal-browser";
import { msalConfig } from "./msalConfig";

let msalInstanceSingleton: PublicClientApplication | null = null;
let msalInitPromise: Promise<void> | null = null;

export function getMsalInstance(): PublicClientApplication {
    if (!msalInstanceSingleton) {
        msalInstanceSingleton = new PublicClientApplication(msalConfig);
    }
    return msalInstanceSingleton;
}

export async function ensureMsalInitialized(): Promise<PublicClientApplication> {
    const instance = getMsalInstance();
    if (!msalInitPromise) {
        msalInitPromise = instance.initialize();
    }
    await msalInitPromise;
    return instance;
}