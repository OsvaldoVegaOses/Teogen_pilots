"use client";

import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { loginRequest } from "@/lib/msalConfig";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function Login() {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessingRedirect, setIsProcessingRedirect] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  // Handle the redirect response from Microsoft
  useEffect(() => {
    console.log("[Login] Component mounted. inProgress:", inProgress, "accounts:", accounts.length, "isAuthenticated:", isAuthenticated);

    // If MSAL is still processing (handleRedirectPromise in progress), wait
    if (inProgress !== "none") {
      console.log("[Login] MSAL interaction in progress:", inProgress);
      setIsProcessingRedirect(true);
      return;
    }

    // MSAL is done processing
    setIsProcessingRedirect(false);

    // If the user is authenticated, redirect to dashboard
    if (isAuthenticated && accounts.length > 0) {
      console.log("[Login] User is authenticated, redirecting to /dashboard. Account:", accounts[0]?.username);
      router.replace("/dashboard/");
    }
  }, [inProgress, isAuthenticated, accounts, router]);

  const handleLogin = async () => {
    setIsLoading(true);
    setAuthError(null);
    try {
      console.log("[Login] Starting loginRedirect...");
      await instance.loginRedirect(loginRequest);
    } catch (e: unknown) {
      console.error("[Login] loginRedirect error:", e);
      setAuthError(e instanceof Error ? e.message : "Error al iniciar sesión. Intenta de nuevo.");
      setIsLoading(false);
    }
  };

  // Show loading screen while processing the redirect
  if (isProcessingRedirect || (isAuthenticated && accounts.length > 0)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <div className="text-center space-y-4">
          <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-lg bg-indigo-600 font-bold text-white text-xl animate-pulse">
            T
          </div>
          <p className="text-zinc-600 dark:text-zinc-400 text-sm animate-pulse">
            {isAuthenticated ? "Redirigiendo al dashboard..." : "Procesando autenticación..."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 font-sans text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
      <header className="fixed top-0 z-50 w-full border-b border-zinc-200/50 bg-zinc-50/80 backdrop-blur-md dark:border-zinc-800/50 dark:bg-zinc-950/80">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">
              T
            </div>
            <span className="text-xl font-bold tracking-tight">TheoGen</span>
          </div>
          <nav className="hidden items-center gap-8 md:flex">
            <Link href="/#features" className="text-sm font-medium hover:text-indigo-600 transition-colors">Características</Link>
            <Link href="/#methodology" className="text-sm font-medium hover:text-indigo-600 transition-colors">Metodología</Link>
            <Link href="/#pricing" className="text-sm font-medium hover:text-indigo-600 transition-colors">Precios</Link>
          </nav>
          <div className="flex items-center gap-4">
            {/* Empty right side in login page to focus on task */}
          </div>
        </div>
      </header>

      <main className="flex-1 pt-16 flex items-center justify-center">
        <div className="w-full max-w-md space-y-8 p-8 bg-white dark:bg-zinc-900 rounded-2xl shadow-xl border border-zinc-200 dark:border-zinc-800">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Bienvenido</h2>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">Inicia sesión con tu cuenta corporativa o de Microsoft para acceder a TheoGen.</p>
          </div>

          {authError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
              <p className="text-sm text-red-700 dark:text-red-400">{authError}</p>
            </div>
          )}

          <div className="mt-8 space-y-6">
            <button
              onClick={handleLogin}
              disabled={isLoading}
              className="group relative flex w-full justify-center rounded-md border border-transparent bg-indigo-600 py-3 px-4 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-70 disabled:cursor-not-allowed transition-all"
            >
              <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                <svg className="h-5 w-5 text-indigo-500 group-hover:text-indigo-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                </svg>
              </span>
              {isLoading ? "Redirigiendo..." : "Iniciar Sesión con Microsoft"}
            </button>

            <div className="mt-6">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-zinc-300 dark:border-zinc-700" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="bg-white dark:bg-zinc-900 px-2 text-zinc-500">
                    O
                  </span>
                </div>
              </div>

              <div className="mt-6 text-center text-xs text-zinc-500">
                <p>Al continuar, aceptas nuestros <Link href="/terms" className="underline hover:text-indigo-500">Términos de Servicio</Link> y <Link href="/privacy" className="underline hover:text-indigo-500">Política de Privacidad</Link>.</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}