import Link from "next/link";

const workflowSteps = [
  "Centraliza entrevistas y fragmentos relevantes.",
  "Detecta patrones y relaciones críticas en el núcleo lógico.",
  "Recupera evidencia focalizada en el núcleo semántico.",
  "Genera conclusiones trazables por claim + evidencia.",
];

const audience = [
  "Estrategia y Transformación",
  "UX Research e Insights de Clientes",
  "Asuntos Públicos y Sostenibilidad",
  "Compliance y Riesgo Reputacional",
  "Consultoras e Investigación Aplicada",
];

const segments = [
  { name: "Colegios/Universidades", pain: "Mejorar experiencia educativa y engagement con apoderados.", cta: "Probar gratis en educación", key: "educacion" },
  { name: "ONGs", pain: "Entender necesidades de la comunidad y demostrar impacto a donantes.", cta: "Probar gratis para ONG", key: "ong" },
  { name: "Estudios de Mercado", pain: "Acelerar análisis cualitativo y aumentar margen operativo.", cta: "Probar gratis en research", key: "market-research" },
  { name: "Empresas B2C", pain: "Mejorar servicio al cliente y fortalecer retención.", cta: "Probar gratis en B2C", key: "b2c" },
  { name: "Consultoras", pain: "Diferenciar el servicio y entregar resultados más rápido.", cta: "Probar gratis en consultoría", key: "consultoria" },
  { name: "Gobierno/Municipios", pain: "Mejorar participación ciudadana y transparencia.", cta: "Probar gratis en sector público", key: "sector-publico" },
];

export default function ResumenPage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-zinc-50 px-6 py-10 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="ambient-glow absolute left-1/2 top-[-210px] h-[480px] w-[480px] -translate-x-1/2 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="ambient-line absolute left-[-8%] top-[24%] h-px w-[116%] bg-gradient-to-r from-transparent via-indigo-500/35 to-transparent" />
        <div className="ambient-line absolute left-[-12%] top-[68%] h-px w-[124%] bg-gradient-to-r from-transparent via-violet-500/25 to-transparent [animation-delay:1.3s]" />
      </div>

      <div className="mx-auto max-w-5xl space-y-8">
        <header className="space-y-4 rounded-3xl border border-zinc-200/70 bg-white/80 p-8 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-900/65">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">Resumen Ejecutivo</p>
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            TheoGen — Plataforma corporativa de insights cualitativos trazables
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Convierte entrevistas, testimonios y evidencia de campo en decisiones trazables y defendibles.
          </p>
        </header>

        <section className="rounded-2xl border border-zinc-200/80 bg-white/85 p-6 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70">
          <h2 className="text-2xl font-bold tracking-tight">Valor para el negocio</h2>
          <div className="mt-4 grid gap-3">
            {[
              "Reduce semanas de análisis manual a ciclos más rápidos.",
              "Mejora la calidad del insight con evidencia verificable.",
              "Disminuye riesgo de interpretaciones no sustentadas.",
              "Estandariza cómo la organización genera conocimiento cualitativo.",
            ].map((item) => (
              <div key={item} className="audience-card rounded-xl border border-zinc-200/80 bg-white/90 p-4 dark:border-zinc-800 dark:bg-zinc-900/70">
                <div className="flex items-center gap-3">
                  <div className="h-2.5 w-2.5 rounded-full bg-indigo-500 opacity-80" />
                  <p className="text-sm text-zinc-700 dark:text-zinc-300">{item}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-zinc-200/80 bg-white/85 p-6 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70">
          <h2 className="text-2xl font-bold tracking-tight">Cómo funciona</h2>
          <div className="mt-4 grid gap-3">
            {workflowSteps.map((step, index) => (
              <div
                key={step}
                className="workflow-card relative overflow-hidden rounded-xl border border-zinc-200/80 bg-white/90 p-4 dark:border-zinc-800 dark:bg-zinc-900/70"
              >
                <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-indigo-500 via-violet-500 to-indigo-500" />
                <div className="flex items-start gap-3 pl-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">
                    {index + 1}
                  </div>
                  <p className="text-sm text-zinc-700 dark:text-zinc-300">{step}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-zinc-200/80 bg-white/85 p-6 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70">
          <h2 className="text-2xl font-bold tracking-tight">Para quién es ideal</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {audience.map((item) => (
              <div key={item} className="audience-card rounded-xl border border-zinc-200/80 bg-white/90 p-4 dark:border-zinc-800 dark:bg-zinc-900/70">
                <div className="flex items-center gap-3">
                  <div className="h-2.5 w-2.5 rounded-full bg-indigo-500 opacity-80" />
                  <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{item}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-zinc-200/80 bg-white/85 p-6 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70">
          <h2 className="text-2xl font-bold tracking-tight">Posicionamiento recomendado</h2>
          <p className="mt-2 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            TheoGen ha sido diseñada como una plataforma corporativa de insights que combina velocidad operativa con rigor
            metodológico, permitiendo que cada hallazgo sea trazable, auditable y útil para decidir.
          </p>
        </section>

        <section className="rounded-2xl border border-zinc-200/80 bg-white/85 p-6 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/70">
          <h2 className="text-2xl font-bold tracking-tight">Pensado para estos segmentos</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {segments.map((segment) => (
              <div key={segment.name} className="audience-card rounded-xl border border-zinc-200/80 bg-white/90 p-4 dark:border-zinc-800 dark:bg-zinc-900/70">
                <div className="flex items-start gap-3">
                  <div className="h-2.5 w-2.5 rounded-full bg-violet-500 opacity-80" />
                  <div>
                    <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{segment.name}</p>
                    <p className="mt-1 text-xs leading-5 text-zinc-600 dark:text-zinc-400">{segment.pain}</p>
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
        </section>

        <footer className="flex flex-wrap gap-3">
          <Link href="/login" className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700">
            Probar gratis
          </Link>
          <Link href="/" className="rounded-xl border border-zinc-300 px-4 py-2 text-sm font-bold hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800">
            Volver al inicio
          </Link>
        </footer>
      </div>
    </main>
  );
}
