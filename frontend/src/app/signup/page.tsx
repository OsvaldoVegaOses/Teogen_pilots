"use client";

import { useMsal } from "@azure/msal-react";
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

export default function Signup() {
  const { instance, accounts } = useMsal();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const segmentKey = (searchParams.get("segment") || "").toLowerCase();
  const segmentLabel = SEGMENT_LABELS[segmentKey] || null;

  useEffect(() => {
    if (accounts.length > 0 || getGoogleToken()) {
      router.push(segmentKey ? `/dashboard?segment=${segmentKey}` : "/dashboard/");
    }
  }, [accounts, router, segmentKey]);

  const handleSignup = async () => {
    setIsLoading(true);
    setAuthError(null);
    try {
      await instance.loginRedirect(loginRequest);
    } catch (e) {
      console.error(e);
      setAuthError(e instanceof Error ? e.message : "Error al crear cuenta. Intenta nuevamente.");
      setIsLoading(false);
    }
  };

  const handleGoogleSuccess = (credential: string): void => {
    setGoogleToken(credential);
    router.push(segmentKey ? `/dashboard?segment=${segmentKey}` : "/dashboard/");
  };

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
            <Link href="/#valor" className="text-sm font-medium hover:text-indigo-600 transition-colors">Valor</Link>
            <Link href="/#como-funciona" className="text-sm font-medium hover:text-indigo-600 transition-colors">Cómo funciona</Link>
            <Link href="/#industrias" className="text-sm font-medium hover:text-indigo-600 transition-colors">Industrias</Link>
          </nav>
          <div className="flex items-center gap-4">
            {/* Empty right side in signup page */}
          </div>
        </div>
      </header>

      <main className="flex-1 pt-16 flex items-center justify-center">
        <div className="w-full max-w-md space-y-8 p-8 bg-white dark:bg-zinc-900 rounded-2xl shadow-xl border border-zinc-200 dark:border-zinc-800">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Crear Cuenta</h2>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">Prueba TheoGen gratis usando tu cuenta de Microsoft o Google.</p>
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
              onClick={handleSignup}
              disabled={isLoading}
              className="group relative flex w-full justify-center rounded-md border border-transparent bg-indigo-600 py-3 px-4 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-70 disabled:cursor-not-allowed transition-all"
            >
              <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                <svg className="h-5 w-5 text-indigo-500 group-hover:text-indigo-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                </svg>
              </span>
              {isLoading ? "Redirigiendo..." : "Registrarse con Microsoft"}
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
                onError={() => setAuthError("Error al crear cuenta con Google. Intenta de nuevo.")}
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
                    ¿Ya tienes cuenta? <Link href={segmentKey ? `/login?segment=${segmentKey}` : "/login"} className="text-indigo-600 hover:text-indigo-500 ml-1">Inicia sesión</Link>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
