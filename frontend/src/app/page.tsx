 "use client";

import Link from "next/link";
import InsightIconCard from "@/components/marketing/InsightIconCard";
import LandingChatbot from "@/components/marketing/LandingChatbot";
import { useEffect, useRef, useState } from "react";

const valueCards: Array<{ title: string; description: string; iconType: "traceability" | "actionable_insights" | "risk_control" | "interview_network" | "pattern_detection" | "evidence_traceability" }> = [
  {
    title: "Trazabilidad por Claim",
    description: "Cada conclusión conecta con evidencia verificable para auditoría y confianza ejecutiva.",
    iconType: "traceability",
  },
  {
    title: "Insights Accionables",
    description: "Convierte entrevistas en decisiones con foco en impacto, cobertura y contraste real.",
    iconType: "actionable_insights",
  },
  {
    title: "Control de Riesgo",
    description: "Validación determinista para reducir deriva y evitar conclusiones sin soporte.",
    iconType: "risk_control",
  },
  {
    title: "Entrevistas Centralizadas",
    description: "Unifica múltiples voces y contextos en una base coherente para análisis corporativo.",
    iconType: "interview_network",
  },
  {
    title: "Patrones Detectados",
    description: "Identifica relaciones semánticas clave para detectar señales y oportunidades tempranas.",
    iconType: "pattern_detection",
  },
  {
    title: "Evidencia Trazable",
    description: "Cada hallazgo queda respaldado por fragmentos verificables para reportes defendibles.",
    iconType: "evidence_traceability",
  },
];

const audience = [
  "Estrategia y Transformación",
  "UX Research e Insights",
  "Asuntos Públicos y Sostenibilidad",
  "Compliance y Riesgo Reputacional",
];

const workflowSteps = [
  "Centraliza entrevistas y fragmentos relevantes.",
  "Detecta patrones y relaciones críticas en el núcleo lógico.",
  "Recupera evidencia focalizada en el núcleo semántico.",
  "Genera conclusiones trazables por claim + evidencia.",
];

const segments = [
  { name: "Colegios/Universidades", pain: "Mejorar experiencia educativa y engagement con apoderados.", cta: "Probar gratis en educación", key: "educacion" },
  { name: "ONGs", pain: "Entender necesidades de la comunidad y demostrar impacto a donantes.", cta: "Probar gratis para ONG", key: "ong" },
  { name: "Estudios de Mercado", pain: "Acelerar análisis cualitativo y aumentar margen operativo.", cta: "Probar gratis en research", key: "market-research" },
  { name: "Empresas B2C", pain: "Mejorar servicio al cliente y fortalecer retención.", cta: "Probar gratis en B2C", key: "b2c" },
  { name: "Consultoras", pain: "Diferenciar el servicio y entregar resultados más rápido.", cta: "Probar gratis en consultoría", key: "consultoria" },
  { name: "Gobierno/Municipios", pain: "Mejorar participación ciudadana y transparencia.", cta: "Probar gratis en sector público", key: "sector-publico" },
];

export default function Home() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const mobileMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const mobileDrawerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    document.body.style.overflow = mobileNavOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileNavOpen]);

  useEffect(() => {
    if (!mobileNavOpen) return;

    const focusable = mobileDrawerRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable?.[0];
    const last = focusable?.[focusable.length - 1];
    first?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      mobileMenuButtonRef.current?.focus();
    };
  }, [mobileNavOpen]);

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 font-sans text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
      {mobileNavOpen && (
        <button
          type="button"
          onClick={() => setMobileNavOpen(false)}
          className="fixed inset-0 z-40 bg-black/40 md:hidden motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-150"
          aria-label="Cerrar menu"
        />
      )}
      <header className="fixed top-0 z-50 w-full border-b border-zinc-200/50 bg-zinc-50/80 backdrop-blur-md dark:border-zinc-800/50 dark:bg-zinc-950/80">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">T</div>
            <span className="text-xl font-bold tracking-tight">TheoGen</span>
          </div>
          <nav className="hidden items-center gap-8 md:flex">
            <Link href="#valor" className="text-sm font-medium hover:text-indigo-600 transition-colors">Valor</Link>
            <Link href="#como-funciona" className="text-sm font-medium hover:text-indigo-600 transition-colors">Cómo funciona</Link>
            <Link href="#para-quien" className="text-sm font-medium hover:text-indigo-600 transition-colors">Para quién</Link>
            <Link href="#industrias" className="text-sm font-medium hover:text-indigo-600 transition-colors">Industrias</Link>
            <Link href="/resumen" className="text-sm font-medium hover:text-indigo-600 transition-colors">Resumen</Link>
          </nav>
          <div className="hidden items-center gap-4 md:flex">
            <Link href="/login" className="text-sm font-medium hover:text-indigo-600 transition-colors">Entrar</Link>
            <Link href="/login" className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition-all hover:bg-indigo-700">
              Probar gratis
            </Link>
          </div>
          <button
            ref={mobileMenuButtonRef}
            type="button"
            onClick={() => setMobileNavOpen(true)}
            className="rounded-xl border border-zinc-200 px-3 py-1.5 text-xs font-bold hover:bg-zinc-50 dark:border-zinc-700 md:hidden"
            aria-expanded={mobileNavOpen}
            aria-controls="landing-mobile-drawer"
            aria-haspopup="dialog"
          >
            Menu
          </button>
        </div>
      </header>
      <aside
        id="landing-mobile-drawer"
        ref={mobileDrawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Menu de navegacion movil"
        className={`fixed right-0 top-0 z-50 h-full w-72 border-l border-zinc-200 bg-white p-6 transition-transform duration-200 ease-out dark:border-zinc-800 dark:bg-zinc-950 md:hidden ${
          mobileNavOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-center justify-between">
          <span className="text-base font-bold tracking-tight">Navegacion</span>
          <button
            type="button"
            onClick={() => setMobileNavOpen(false)}
            className="rounded-lg border border-zinc-200 px-2 py-1 text-xs font-semibold dark:border-zinc-700"
          >
            Cerrar
          </button>
        </div>
        <nav className="flex flex-col gap-2">
          <Link href="#valor" onClick={() => setMobileNavOpen(false)} className="rounded-xl px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900">Valor</Link>
          <Link href="#como-funciona" onClick={() => setMobileNavOpen(false)} className="rounded-xl px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900">Cómo funciona</Link>
          <Link href="#para-quien" onClick={() => setMobileNavOpen(false)} className="rounded-xl px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900">Para quién</Link>
          <Link href="#industrias" onClick={() => setMobileNavOpen(false)} className="rounded-xl px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900">Industrias</Link>
          <Link href="/resumen" onClick={() => setMobileNavOpen(false)} className="rounded-xl px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-900">Resumen</Link>
        </nav>
        <div className="mt-6 space-y-2">
          <Link href="/login" onClick={() => setMobileNavOpen(false)} className="block rounded-xl border border-zinc-200 px-3 py-2 text-center text-sm font-semibold dark:border-zinc-700">
            Entrar
          </Link>
          <Link href="/login" onClick={() => setMobileNavOpen(false)} className="block rounded-xl bg-indigo-600 px-3 py-2 text-center text-sm font-semibold text-white">
            Probar gratis
          </Link>
        </div>
      </aside>

      <main className="flex-1 pt-16">
        <section className="relative overflow-hidden py-16 sm:py-24 md:py-32">
          <div className="absolute inset-0 -z-10">
            <div className="ambient-glow absolute left-1/2 top-[-180px] h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-indigo-500/20 blur-3xl" />
            <div className="ambient-line absolute left-[-10%] top-1/3 h-px w-[120%] bg-gradient-to-r from-transparent via-indigo-500/35 to-transparent" />
            <div className="ambient-line absolute left-[-15%] top-2/3 h-px w-[130%] bg-gradient-to-r from-transparent via-violet-500/25 to-transparent [animation-delay:1.5s]" />
          </div>
          <div className="mx-auto max-w-7xl px-4 text-center sm:px-6">
            <h1 className="mx-auto max-w-5xl text-4xl font-extrabold tracking-tight sm:text-5xl md:text-7xl">
              Plataforma corporativa de{" "}
              <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
                insights cualitativos trazables
              </span>
            </h1>
            <p className="mx-auto mt-6 max-w-3xl text-base leading-7 text-zinc-700 dark:text-zinc-300 sm:mt-8 sm:text-lg sm:leading-8">
              TheoGen convierte entrevistas y evidencia de campo en decisiones claras, accionables y defendibles ante dirección.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/login" className="h-14 w-full rounded-2xl bg-indigo-600 px-8 flex items-center justify-center text-lg font-bold text-white transition-all hover:bg-indigo-700 sm:w-auto">
                Probar gratis
              </Link>
              <Link href="/resumen" className="h-14 w-full rounded-2xl border border-zinc-200 bg-white/70 px-8 flex items-center justify-center text-lg font-bold backdrop-blur-sm transition-all hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:bg-zinc-900 sm:w-auto">
                Ver resumen ejecutivo
              </Link>
            </div>
            <div className="mx-auto mt-8 max-w-md">
              <div className="status-sweep relative flex items-center justify-between overflow-hidden rounded-xl border border-zinc-200/70 bg-white/75 px-4 py-3 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/60">
                <div className="flex items-center gap-3">
                  <div className="status-dot-pulse h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  <span className="text-xs font-mono tracking-wider text-zinc-600 dark:text-zinc-300">
                    INSIGHTS SYNC
                  </span>
                </div>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-4 w-4 text-emerald-500"
                  aria-hidden="true"
                >
                  <path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2" />
                </svg>
              </div>
            </div>
          </div>
        </section>

        <section id="valor" className="bg-white py-16 dark:bg-zinc-900/50 sm:py-20">
          <div className="mx-auto max-w-7xl px-4 sm:px-6">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Valor para el negocio</h2>
              <p className="mt-4 text-zinc-700 dark:text-zinc-300">Velocidad operativa, calidad analítica y evidencia verificable.</p>
            </div>
            <div className="mt-12 grid gap-8 md:grid-cols-2 xl:grid-cols-3">
              {valueCards.map((card, index) => (
                <InsightIconCard
                  key={card.title}
                  title={card.title}
                  description={card.description}
                  iconType={card.iconType}
                  delayMs={index * 90}
                />
              ))}
            </div>
          </div>
        </section>

        <section id="como-funciona" className="py-16 sm:py-20">
          <div className="mx-auto max-w-5xl px-4 sm:px-6">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl text-center">Cómo funciona</h2>
            <div className="mt-10 grid gap-4">
              {workflowSteps.map((step, index) => (
                <div
                  key={step}
                  className="workflow-card relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white/80 p-5 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70"
                >
                  <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-indigo-500 via-violet-500 to-indigo-500" />
                  <div className="flex items-start gap-4 pl-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600/90 text-sm font-bold text-white">
                      {index + 1}
                    </div>
                    <p className="pt-1 text-sm leading-7 text-zinc-700 dark:text-zinc-300">{step}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="para-quien" className="bg-white py-16 dark:bg-zinc-900/50 sm:py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl text-center">Para quién es ideal</h2>
            <div className="mt-10 grid gap-4 md:grid-cols-2">
              {audience.map((item) => (
                <div
                  key={item}
                  className="audience-card rounded-2xl border border-zinc-200/80 bg-white/85 p-5 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70"
                >
                  <div className="flex items-center gap-3">
                    <div className="h-2.5 w-2.5 rounded-full bg-indigo-500 opacity-80" />
                    <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{item}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="industrias" className="py-16 sm:py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl text-center">Pensado para estos segmentos</h2>
            <div className="mt-10 grid gap-4 md:grid-cols-2">
              {segments.map((segment) => (
                <div
                  key={segment.name}
                  className="audience-card rounded-2xl border border-zinc-200/80 bg-white/85 p-5 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70"
                >
                  <div className="flex items-start gap-3">
                    <div className="h-2.5 w-2.5 rounded-full bg-violet-500 opacity-80" />
                    <div>
                      <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{segment.name}</p>
                      <p className="mt-1 text-xs leading-5 text-zinc-700 dark:text-zinc-300">{segment.pain}</p>
                      <Link
                        href={`/login?segment=${segment.key}`}
                        className="mt-3 inline-flex rounded-lg border border-indigo-200 bg-indigo-50/70 px-3 py-1.5 text-xs font-semibold text-indigo-700 transition-colors hover:bg-indigo-100 dark:border-indigo-900/70 dark:bg-indigo-950/40 dark:text-indigo-300 dark:hover:bg-indigo-900/40"
                      >
                        {segment.cta}
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
      <footer className="border-t border-zinc-200 py-10 dark:border-zinc-800">
        <div className="mx-auto grid max-w-7xl gap-6 px-4 sm:px-6 md:grid-cols-3 md:items-start">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-indigo-600 text-xs font-bold text-white">T</div>
            <span className="font-bold">TheoGen</span>
          </div>

          <div className="space-y-1 text-sm text-zinc-600 dark:text-zinc-300">
            <p>Contacto empresarial:</p>
            <a href="mailto:axial@nubeweb.cl" className="block hover:text-indigo-600">axial@nubeweb.cl</a>
            <a href="mailto:theogen@nubeweb.cl" className="block hover:text-indigo-600">theogen@nubeweb.cl</a>
            <a href="https://axial.nubeweb.cl" target="_blank" rel="noopener noreferrer" className="block hover:text-indigo-600">
              axial.nubeweb.cl
            </a>
            <p>Osvaldo Vega Oses, Sociologo</p>
          </div>

          <div className="flex flex-col gap-2 text-xs text-zinc-600 dark:text-zinc-300 md:items-end">
            <p>� 2026 TheoGen. Corporate Qualitative Insights Platform.</p>
            <div className="flex gap-6">
              <Link href="/resumen" className="text-xs text-zinc-600 hover:text-indigo-600 dark:text-zinc-300">Resumen ejecutivo</Link>
              <Link href="/login" className="text-xs text-zinc-600 hover:text-indigo-600 dark:text-zinc-300">Probar gratis</Link>
            </div>
          </div>
        </div>
      </footer>
      <LandingChatbot />
    </div>
  );
}
