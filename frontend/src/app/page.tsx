import Link from "next/link";

const valueCards = [
  {
    title: "Trazabilidad por Claim",
    description: "Cada conclusión conecta con evidencia verificable para auditoría y confianza ejecutiva.",
    icon: "◎",
  },
  {
    title: "Insights Accionables",
    description: "Convierte entrevistas en decisiones con foco en impacto, cobertura y contraste real.",
    icon: "◈",
  },
  {
    title: "Control de Riesgo",
    description: "Validación determinista para reducir deriva y evitar conclusiones sin soporte.",
    icon: "◉",
  },
];

const audience = [
  "Estrategia y Transformación",
  "UX Research e Insights",
  "Asuntos Públicos y Sostenibilidad",
  "Compliance y Riesgo Reputacional",
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 font-sans text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
      <header className="fixed top-0 z-50 w-full border-b border-zinc-200/50 bg-zinc-50/80 backdrop-blur-md dark:border-zinc-800/50 dark:bg-zinc-950/80">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">T</div>
            <span className="text-xl font-bold tracking-tight">TheoGen</span>
          </div>
          <nav className="hidden items-center gap-8 md:flex">
            <Link href="#valor" className="text-sm font-medium hover:text-indigo-600 transition-colors">Valor</Link>
            <Link href="#como-funciona" className="text-sm font-medium hover:text-indigo-600 transition-colors">Cómo funciona</Link>
            <Link href="#para-quien" className="text-sm font-medium hover:text-indigo-600 transition-colors">Para quién</Link>
            <Link href="/resumen" className="text-sm font-medium hover:text-indigo-600 transition-colors">Resumen</Link>
          </nav>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-sm font-medium hover:text-indigo-600 transition-colors">Entrar</Link>
            <Link href="/dashboard" className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition-all hover:bg-indigo-700">
              Solicitar demo
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 pt-16">
        <section className="relative overflow-hidden py-24 md:py-32">
          <div className="absolute inset-0 -z-10">
            <div className="ambient-glow absolute left-1/2 top-[-180px] h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-indigo-500/20 blur-3xl" />
            <div className="ambient-line absolute left-[-10%] top-1/3 h-px w-[120%] bg-gradient-to-r from-transparent via-indigo-500/35 to-transparent" />
            <div className="ambient-line absolute left-[-15%] top-2/3 h-px w-[130%] bg-gradient-to-r from-transparent via-violet-500/25 to-transparent [animation-delay:1.5s]" />
          </div>
          <div className="mx-auto max-w-7xl px-6 text-center">
            <h1 className="mx-auto max-w-5xl text-5xl font-extrabold tracking-tight md:text-7xl">
              Plataforma corporativa de{" "}
              <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
                insights cualitativos trazables
              </span>
            </h1>
            <p className="mx-auto mt-8 max-w-3xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
              TheoGen convierte entrevistas y evidencia de campo en decisiones claras, accionables y defendibles ante dirección.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/dashboard" className="h-14 w-full rounded-2xl bg-indigo-600 px-8 flex items-center justify-center text-lg font-bold text-white transition-all hover:bg-indigo-700 sm:w-auto">
                Agendar piloto
              </Link>
              <Link href="/resumen" className="h-14 w-full rounded-2xl border border-zinc-200 bg-white/70 px-8 flex items-center justify-center text-lg font-bold backdrop-blur-sm transition-all hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:bg-zinc-900 sm:w-auto">
                Ver resumen ejecutivo
              </Link>
            </div>
            <div className="mx-auto mt-8 max-w-md">
              <div className="status-sweep relative flex items-center justify-between overflow-hidden rounded-xl border border-zinc-200/70 bg-white/75 px-4 py-3 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/60">
                <div className="flex items-center gap-3">
                  <div className="status-dot-pulse h-2.5 w-2.5 rounded-full bg-emerald-500" />
                  <span className="text-xs font-mono tracking-wider text-zinc-500 dark:text-zinc-400">
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

        <section id="valor" className="py-20 bg-white dark:bg-zinc-900/50">
          <div className="mx-auto max-w-7xl px-6">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Valor para el negocio</h2>
              <p className="mt-4 text-zinc-600 dark:text-zinc-400">Velocidad operativa, calidad analítica y evidencia verificable.</p>
            </div>
            <div className="mt-12 grid gap-8 md:grid-cols-3">
              {valueCards.map((card) => (
                <div key={card.title} className="rounded-3xl border border-zinc-200 p-8 transition-all hover:border-indigo-500/40 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
                  <div className="mb-4 text-3xl text-indigo-600">{card.icon}</div>
                  <h3 className="text-xl font-bold">{card.title}</h3>
                  <p className="mt-2 text-zinc-600 dark:text-zinc-400">{card.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="como-funciona" className="py-20">
          <div className="mx-auto max-w-5xl px-6">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl text-center">Cómo funciona</h2>
            <ol className="mt-10 space-y-4 rounded-3xl border border-zinc-200 bg-white p-8 text-sm leading-7 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
              <li>1. Centraliza entrevistas y fragmentos relevantes.</li>
              <li>2. Detecta patrones y relaciones críticas en el núcleo lógico.</li>
              <li>3. Recupera evidencia focalizada en el núcleo semántico.</li>
              <li>4. Genera conclusiones trazables por claim + evidencia.</li>
            </ol>
          </div>
        </section>

        <section id="para-quien" className="py-20 bg-white dark:bg-zinc-900/50">
          <div className="mx-auto max-w-6xl px-6">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl text-center">Para quién es ideal</h2>
            <div className="mt-10 grid gap-4 md:grid-cols-2">
              {audience.map((item) => (
                <div key={item} className="rounded-2xl border border-zinc-200 bg-white p-5 text-sm font-semibold text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-zinc-200 py-10 dark:border-zinc-800">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-5 px-6 md:flex-row">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-indigo-600 text-xs font-bold text-white">T</div>
            <span className="font-bold">TheoGen</span>
          </div>
          <p className="text-sm text-zinc-500">© 2026 TheoGen. Corporate Qualitative Insights Platform.</p>
          <div className="flex gap-6">
            <Link href="/resumen" className="text-xs text-zinc-500 hover:text-indigo-600">Resumen ejecutivo</Link>
            <Link href="/dashboard" className="text-xs text-zinc-500 hover:text-indigo-600">Solicitar demo</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
