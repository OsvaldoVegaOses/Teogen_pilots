"use client";

import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { GoogleLogin } from "@react-oauth/google";
import { loginRequest } from "@/lib/msalConfig";
import { setGoogleToken, getGoogleToken } from "@/lib/googleAuth";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

const SEGMENT_LABELS: Record<string, string> = {
  educacion: "Educación",
  ong: "ONG",
  "market-research": "Estudios de Mercado",
  b2c: "Empresas B2C",
  consultoria: "Consultoras",
  "sector-publico": "Gobierno/Municipios",
};

export default function Login() {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const segmentKey = (searchParams.get("segment") || "").toLowerCase();
  const segmentLabel = SEGMENT_LABELS[segmentKey] || null;
  const isProcessingRedirect = inProgress !== "none";

  // Handle the redirect response from Microsoft
  useEffect(() => {
    console.log("[Login] Component mounted. inProgress:", inProgress, "accounts:", accounts.length, "isAuthenticated:", isAuthenticated);

    if (isProcessingRedirect) {
      console.log("[Login] MSAL interaction in progress:", inProgress);
      return;
    }

    // Redirect if authenticated via MSAL or Google
    const destination = segmentKey ? `/dashboard?segment=${segmentKey}` : "/dashboard/";
    if (isAuthenticated && accounts.length > 0) {
      console.log("[Login] MSAL authenticated, redirecting to dashboard.");
      router.replace(destination);
    } else if (getGoogleToken()) {
      console.log("[Login] Google token found, redirecting to dashboard.");
      router.replace(destination);
    }
  }, [inProgress, isAuthenticated, accounts, router, segmentKey, isProcessingRedirect]);

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

  const handleGoogleSuccess = (credential: string): void => {
    console.log("[Login] Google id_token received, storing and redirecting.");
    setGoogleToken(credential);
    router.replace(segmentKey ? `/dashboard?segment=${segmentKey}` : "/dashboard/");
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
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[80] focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-zinc-900 dark:focus:bg-zinc-900 dark:focus:text-zinc-100"
      >
        Saltar al contenido principal
      </a>
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

      <main id="main-content" className="flex-1 pt-16 flex items-center justify-center">
        <div className="w-full max-w-md space-y-8 p-8 bg-white dark:bg-zinc-900 rounded-2xl shadow-xl border border-zinc-200 dark:border-zinc-800">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Bienvenido</h2>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">Inicia sesión para continuar tu prueba gratuita de TheoGen.</p>
            {segmentLabel && (
              <p className="mt-3 inline-flex rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 dark:border-indigo-900/70 dark:bg-indigo-950/40 dark:text-indigo-300">
                Segmento seleccionado: {segmentLabel}
              </p>
            )}
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

            <div className="flex w-full justify-center">
              <GoogleLogin
                onSuccess={(cr) => {
                  if (cr.credential) {
                    handleGoogleSuccess(cr.credential);
                  } else {
                    setAuthError("No se recibió el token de Google.");
                  }
                }}
                onError={() => setAuthError("Error al iniciar sesión con Google. Intenta de nuevo.")}
                theme="outline"
                size="large"
                text="continue_with"
                shape="rectangular"
                width={320}
              />
            </div>

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
                <p className="mb-2">
                  ¿Aún no tienes cuenta?{" "}
                  <Link href={segmentKey ? `/signup?segment=${segmentKey}` : "/signup"} className="underline hover:text-indigo-500">
                    Crear cuenta
                  </Link>
                </p>
                <p>Al continuar, aceptas nuestros <Link href="/#" className="underline hover:text-indigo-500">Términos de Servicio</Link> y <Link href="/#" className="underline hover:text-indigo-500">Política de Privacidad</Link>.</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
