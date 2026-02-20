import Link from "next/link";

export default function Home() {
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
            <Link href="#features" className="text-sm font-medium hover:text-indigo-600 transition-colors">Características</Link>
            <Link href="#methodology" className="text-sm font-medium hover:text-indigo-600 transition-colors">Metodología</Link>
            <Link href="#pricing" className="text-sm font-medium hover:text-indigo-600 transition-colors">Precios</Link>
          </nav>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-sm font-medium hover:text-indigo-600 transition-colors">Entrar</Link>
            <Link 
              href="/signup" 
              className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition-all hover:bg-indigo-700 hover:shadow-lg hover:shadow-indigo-500/30"
            >
              Comenzar gratis
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 pt-16">
        {/* Hero Section */}
        <section className="relative overflow-hidden py-24 md:py-32">
          <div className="absolute inset-0 -z-10 bg-[radial-gradient(45%_45%_at_50%_50%,rgba(79,70,229,0.1)_0%,rgba(255,255,255,0)_100%)] dark:bg-[radial-gradient(45%_45%_at_50%_50%,rgba(79,70,229,0.15)_0%,rgba(0,0,0,0)_100%)]" />
          <div className="mx-auto max-w-7xl px-6 text-center">
            <h1 className="mx-auto max-w-4xl text-5xl font-extrabold tracking-tight md:text-7xl">
              De datos a teoría en <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">días, no meses</span>.
            </h1>
            <p className="mx-auto mt-8 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
              Con el rigor de Expertos y la potencia de la Inteligencia Artificial. TheoGen automatiza el descubrimiento de patrones para investigadores de Teoría Fundamentada.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link 
                href="/dashboard" 
                className="h-14 w-full rounded-2xl bg-indigo-600 px-8 flex items-center justify-center text-lg font-bold text-white transition-all hover:bg-indigo-700 hover:scale-105 active:scale-95 sm:w-auto"
              >
                Crear primer proyecto
              </Link>
              <Link 
                href="#features" 
                className="h-14 w-full rounded-2xl border border-zinc-200 bg-white/50 px-8 flex items-center justify-center text-lg font-bold backdrop-blur-sm transition-all hover:bg-white dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:bg-zinc-900 sm:w-auto"
              >
                Ver Demo
              </Link>
            </div>
            <div className="mt-16 flex items-center justify-center gap-10 text-indigo-600">
              <div className="flex flex-col items-center">
                <div className="text-2xl mb-2">🤖</div>
                <span className="text-sm font-medium">Azure AI</span>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-2xl mb-2">⚡</div>
                <span className="text-sm font-medium">FastAPI</span>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-2xl mb-2">🗄️</div>
                <span className="text-sm font-medium">PostgreSQL</span>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-2xl mb-2">🔄</div>
                <span className="text-sm font-medium">Redis</span>
              </div>
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section id="features" className="py-24 bg-white dark:bg-zinc-900/50">
          <div className="mx-auto max-w-7xl px-6">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Metodología Rigurosa, Proceso Acelerado</h2>
              <p className="mt-4 text-zinc-600 dark:text-zinc-400">Diseñado para investigadores por expertos en IA aplicada.</p>
            </div>
            <div className="mt-16 grid gap-8 md:grid-cols-3">
              {[
                {
                  title: "Detección de Patrones",
                  description: "Clustering semántico y análisis de redes para identificar temas emergentes automáticamente.",
                  icon: "🧩"
                },
                {
                  title: "Generación de Teoría",
                  description: "Asistente inteligente que construye modelos teóricos basados en tus códigos y memos.",
                  icon: "🚀"
                },
                {
                  title: "Validación de Datos",
                  description: "Contro-verificación exhaustiva contra el corpus original para asegurar solidez empírica.",
                  icon: "🔍"
                }
              ].map((feature, i) => (
                <div key={i} className="group relative rounded-3xl border border-zinc-200 p-8 transition-all hover:border-indigo-500/50 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
                  <div className="text-4xl mb-4">{feature.icon}</div>
                  <h3 className="text-xl font-bold">{feature.title}</h3>
                  <p className="mt-2 text-zinc-600 dark:text-zinc-400">{feature.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-zinc-200 py-12 dark:border-zinc-800">
        <div className="mx-auto max-w-7xl px-6 flex flex-col items-center justify-between gap-6 md:flex-row">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-indigo-600 font-bold text-white text-xs">
              T
            </div>
            <span className="font-bold">TheoGen</span>
          </div>
          <p className="text-sm text-zinc-500">© 2026 TheoGen. Built with Azure AI.</p>
          <div className="flex gap-6">
             <Link href="#" className="text-xs text-zinc-500 hover:text-indigo-600">Privacidad</Link>
             <Link href="#" className="text-xs text-zinc-500 hover:text-indigo-600">Términos</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
