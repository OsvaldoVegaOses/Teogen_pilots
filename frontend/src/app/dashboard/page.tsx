"use client";

import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import InterviewUpload from "@/components/InterviewUpload";
import MemoManager from "@/components/MemoManager";
import CodeExplorer from "@/components/CodeExplorer";

export default function Dashboard() {
    const { instance, accounts, inProgress } = useMsal();
    const isAuthenticated = useIsAuthenticated();
    const router = useRouter();

    useEffect(() => {
        // Only redirect if MSAL is done processing and user is not authenticated
        if (inProgress === "none" && !isAuthenticated) {
            console.log("[Dashboard] Not authenticated, redirecting to /login/");
            router.replace("/login/");
        }
    }, [inProgress, isAuthenticated, router]);

    const [projects, setProjects] = useState<any[]>([]);
    const [loadingProjects, setLoadingProjects] = useState(true);
    const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<"overview" | "codes" | "memos">("overview");

    const [activeTheory, setActiveTheory] = useState<any | null>(null);
    const [loadingTheory, setLoadingTheory] = useState(false);
    const [generatingTheory, setGeneratingTheory] = useState(false);
    const [theoryMessage, setTheoryMessage] = useState("");

    // Fetch projects from backend
    useEffect(() => {
        async function fetchProjects() {
            if (!isAuthenticated) return;

            try {
                // Import apiClient dynamically to avoid issues if not used properly in client component
                const { apiClient } = await import("@/lib/api");
                const response = await apiClient("/projects/");

                if (response.ok) {
                    const data = await response.json();
                    setProjects(data);
                } else {
                    console.error("Failed to fetch projects");
                }
            } catch (error) {
                console.error("Error loading projects:", error);
            } finally {
                setLoadingProjects(false);
            }
        }

        if (isAuthenticated) {
            fetchProjects();
        }
    }, [isAuthenticated]);

    // Fetch active theory when project changes
    useEffect(() => {
        async function fetchTheory() {
            if (!selectedProjectId) {
                setActiveTheory(null);
                return;
            }

            setLoadingTheory(true);
            try {
                const { apiClient } = await import("@/lib/api");
                const response = await apiClient(`/projects/${selectedProjectId}/theories`);

                if (response.ok) {
                    const theories = await response.json();
                    // Assuming we want the latest completed theory
                    const latest = theories.find((t: any) => t.status === "completed" || t.status === "draft");
                    setActiveTheory(latest || null);
                }
            } catch (error) {
                console.error("Error fetching theory:", error);
            } finally {
                setLoadingTheory(false);
            }
        }

        fetchTheory();
    }, [selectedProjectId]);

    async function handleSync() {
        setLoadingProjects(true);
        try {
            const { apiClient } = await import("@/lib/api");
            const response = await apiClient("/projects/");
            if (response.ok) {
                const data = await response.json();
                setProjects(data);
            }
        } catch (error) {
            console.error("Error syncing:", error);
        } finally {
            setLoadingProjects(false);
        }
    }

    async function handleCreateProject() {
        const name = prompt("Nombre del nuevo proyecto:");
        if (!name) return;

        try {
            const { apiClient } = await import("@/lib/api");
            const response = await apiClient("/projects/", {
                method: "POST",
                body: JSON.stringify({
                    name,
                    description: "Proyecto de investigación",
                    methodological_profile: "constructivist",
                    language: "es"
                })
            });

            if (response.ok) {
                const newProj = await response.json();
                setProjects(prev => [newProj, ...prev]);
                setSelectedProjectId(newProj.id);
            } else {
                const errData = await response.json().catch(() => ({}));
                alert(`Error al crear proyecto: ${errData.detail || response.statusText}`);
            }
        } catch (error) {
            console.error("Creation error:", error);
            alert("Error de conexión al crear proyecto");
        }
    }

    async function handleGenerateTheory() {
        if (!selectedProjectId || generatingTheory) return;

        setGeneratingTheory(true);
        setTheoryMessage("⏳ Iniciando generación de teoría...");

        try {
            const { apiClient } = await import("@/lib/api");

            // 1. Enqueue — returns 202 with task_id immediately
            const enqueueResp = await apiClient(`/projects/${selectedProjectId}/generate-theory`, {
                method: "POST",
                body: JSON.stringify({
                    min_interviews: 1,
                    use_model_router: true,
                }),
            });

            if (!enqueueResp.ok) {
                const err = await enqueueResp.json().catch(() => ({}));
                setTheoryMessage(`❌ ${err.detail || "No se pudo iniciar la generación."}`);
                setGeneratingTheory(false);
                return;
            }

            const enqueueData = await enqueueResp.json();
            const { task_id } = enqueueData;
            setTheoryMessage("⏳ Generando teoría... (puede tardar entre 2 y 10 minutos según el volumen de datos)");

            // 2. Poll with adaptive delay until completed or failed (max 10 min)
            let attempts = 0;
            const maxAttempts = 120; // 10 min max
            let nextDelayMs = Math.max(2000, (enqueueData.next_poll_seconds || 5) * 1000);
            const STEP_LABELS: Record<number, string> = {
                6:  "Analizando categorías...",
                12: "Construyendo grafo de conocimiento...",
                24: "Calculando métricas de red...",
                36: "Generando embeddings semánticos...",
                48: "Identificando categoría central...",
                60: "Construyendo paradigma Straussiano...",
                72: "Analizando saturación teórica...",
                90: "Guardando teoría en base de datos...",
            };
            const poll = async () => {
                attempts++;
                try {
                    const statusResp = await apiClient(
                        `/projects/${selectedProjectId}/generate-theory/status/${task_id}`
                    );
                    if (!statusResp.ok) {
                        setTheoryMessage("❌ Error al consultar estado de la tarea.");
                        setGeneratingTheory(false);
                        return;
                    }
                    const taskData = await statusResp.json();
                    nextDelayMs = Math.max(2000, (taskData.next_poll_seconds || 5) * 1000);

                    if (taskData.status === "completed") {
                        setActiveTheory(taskData.result);
                        setTheoryMessage("✅ Teoría generada correctamente.");
                        setGeneratingTheory(false);
                        return;
                    }
                    if (taskData.status === "failed") {
                        setTheoryMessage(`❌ ${taskData.error || "La generación falló."}`);
                        setGeneratingTheory(false);
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        setTheoryMessage("❌ Tiempo de espera agotado (10 min). El proceso continúa en segundo plano — recarga en unos minutos.");
                        setGeneratingTheory(false);
                        return;
                    }

                    const elapsed = attempts * Math.round(nextDelayMs / 1000);
                    const stepMsg = taskData.step ? `Etapa: ${taskData.step}` : (STEP_LABELS[attempts] ?? "");
                    const dots = ".".repeat((attempts % 3) + 1);
                    setTheoryMessage(`⏳ ${stepMsg || `Generando teoría${dots}`} (${elapsed}s / ~10 min máx)`);

                    // Gentle backoff to reduce backend pressure on long jobs.
                    if (attempts > 12) {
                        nextDelayMs = Math.min(15000, Math.round(nextDelayMs * 1.15));
                    }
                    setTimeout(poll, nextDelayMs);
                } catch {
                    setTheoryMessage("❌ Error de conexión al consultar estado.");
                    setGeneratingTheory(false);
                }
            };
            setTimeout(poll, nextDelayMs);

        } catch (error) {
            console.error("Error generating theory:", error);
            setTheoryMessage("❌ Error de conexión al generar teoría.");
            setGeneratingTheory(false);
        }
    }

    return (
        <div className="flex h-screen bg-zinc-50 dark:bg-black overflow-hidden">
            {/* Sidebar */}
            <aside className="w-64 border-r border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950 shrink-0">
                <div className="flex items-center gap-2 mb-10">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">
                        T
                    </div>
                    <span className="text-xl font-bold tracking-tight dark:text-white">TheoGen</span>
                </div>
                <nav className="flex flex-col gap-2">
                    <button
                        onClick={() => setActiveTab("overview")}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'overview' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'}`}
                    >
                        📊 Dashboard
                    </button>
                    <button
                        onClick={() => setActiveTab("codes")}
                        disabled={!selectedProjectId}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'codes' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'} ${!selectedProjectId ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        📚 Libro de Códigos
                    </button>
                    <button
                        onClick={() => setActiveTab("memos")}
                        disabled={!selectedProjectId}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'memos' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'} ${!selectedProjectId ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        📝 Memos
                    </button>
                </nav>
            </aside>

            {/* Main Content Area */}
            <main className="flex-1 flex flex-col min-w-0">
                <header className="flex items-center justify-between p-8 border-b border-zinc-100 bg-white/50 backdrop-blur-sm dark:bg-zinc-950/50 dark:border-zinc-800">
                    <div>
                        <h1 className="text-2xl font-bold dark:text-white">
                            {activeTab === "overview" && "Panel de Control"}
                            {activeTab === "codes" && "Exploración de Conceptos"}
                            {activeTab === "memos" && "Memos Analíticos"}
                        </h1>
                    </div>
                    <div className="flex gap-4">
                        <button
                            onClick={handleSync}
                            className="rounded-2xl border border-zinc-200 px-6 py-2 text-sm font-bold hover:bg-zinc-50 transition-all dark:border-zinc-800 dark:text-white"
                        >
                            Sincronizar Cloud
                        </button>
                        <button
                            onClick={handleCreateProject}
                            className="rounded-2xl bg-indigo-600 px-6 py-2 text-sm font-bold text-white hover:bg-indigo-700 transition-all"
                        >
                            + Nuevo Proyecto
                        </button>
                    </div>
                </header>

                <div className="flex-1 p-8 overflow-y-auto">
                    {activeTab === "overview" && (
                        <div className="grid gap-10 lg:grid-cols-3">
                            <div className="lg:col-span-2 grid gap-6 md:grid-cols-2 self-start">
                                {loadingProjects ? (
                                    <p className="text-zinc-500">Cargando proyectos...</p>
                                ) : projects.length === 0 ? (
                                    <div className="col-span-2 p-10 text-center border-2 border-dashed rounded-3xl border-zinc-200">
                                        <p className="text-zinc-400 mb-4">No tienes proyectos activos.</p>
                                        <button
                                            onClick={handleCreateProject}
                                            className="text-indigo-600 font-bold hover:underline"
                                        >
                                            Crear tu primer proyecto de investigación
                                        </button>
                                    </div>
                                ) : (
                                    projects.map((project) => (
                                        <div
                                            key={project.id}
                                            onClick={() => setSelectedProjectId(project.id)}
                                            className={`cursor-pointer group relative rounded-3xl border p-8 transition-all hover:shadow-xl ${selectedProjectId === project.id ? 'border-indigo-600 bg-white ring-2 ring-indigo-600/10' : 'border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/50'}`}
                                        >
                                            <div className="flex items-start justify-between mb-4">
                                                <span className="text-xs font-bold uppercase tracking-widest text-indigo-600">Active</span>
                                                <span className="text-2xl">📁</span>
                                            </div>
                                            <h3 className="text-xl font-bold dark:text-white truncate" title={project.name}>{project.name}</h3>
                                            <p className="mt-2 text-sm text-zinc-500 line-clamp-2">{project.description || "Sin descripción"}</p>

                                            {/* Progress Bar (Hidden if no saturation data) */}
                                            {project.saturation_score !== undefined && (
                                                <div className="mt-6">
                                                    <div className="flex justify-between text-xs font-bold mb-2 dark:text-zinc-400">
                                                        <span>Progreso de Saturación</span>
                                                        <span>{Math.round(project.saturation_score * 100)}%</span>
                                                    </div>
                                                    <div className="h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
                                                        <div
                                                            className={`[--progress-width:${Math.round(project.saturation_score * 100)}%] progress-bar h-full rounded-full bg-indigo-600 transition-all duration-1000 shadow-[0_0_10px_rgba(79,70,229,0.5)]`}
                                                        />
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ))
                                )}

                                {/* Show active theory if available */}
                                {activeTheory && (
                                    <div className="col-span-2 mt-8">
                                        {/* Import dynamically to avoid SSR issues if necessary, strictly client-side here */}
                                        {(() => {
                                            const TheoryViewer = require("@/components/TheoryViewer").default;
                                            return <TheoryViewer projectId={selectedProjectId!} theory={activeTheory} />;
                                        })()}
                                    </div>
                                )}
                            </div>

                            <div className="space-y-6">
                                {selectedProjectId ? (
                                    <>
                                        <InterviewUpload
                                            projectId={selectedProjectId}
                                            onUploadSuccess={() => console.log("Refresh list...")}
                                        />

                                        {!activeTheory && (
                                            <div className="rounded-3xl bg-indigo-600 p-8 text-white shadow-xl shadow-indigo-500/20">
                                                <h4 className="font-bold mb-2 text-lg">Teorización Assist</h4>
                                                <p className="text-white/80 text-sm mb-6">
                                                    Analiza los datos del proyecto seleccionado para buscar patrones emergentes.
                                                </p>
                                                <button
                                                    className="w-full rounded-xl bg-white py-3 text-sm font-bold text-indigo-600 shadow-lg transition-all hover:scale-102 hover:bg-indigo-50 active:scale-98"
                                                    onClick={handleGenerateTheory}
                                                    disabled={generatingTheory}
                                                >
                                                    {generatingTheory ? "Generando teoría..." : "Generar Teoría (v1.2)"}
                                                </button>
                                                {theoryMessage && (
                                                    <p className="mt-3 text-xs font-medium text-white/90">{theoryMessage}</p>
                                                )}
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <div className="p-8 text-center border-2 border-dashed rounded-3xl border-zinc-200 bg-zinc-50/50">
                                        <p className="text-zinc-400">Selecciona un proyecto para ver acciones disponibles.</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {activeTab === "codes" && selectedProjectId && (
                        <div className="h-full">
                            <CodeExplorer projectId={selectedProjectId} />
                        </div>
                    )}

                    {activeTab === "memos" && selectedProjectId && (
                        <div className="max-w-4xl mx-auto">
                            <MemoManager projectId={selectedProjectId} />
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
