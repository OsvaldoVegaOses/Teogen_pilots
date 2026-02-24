"use client";

import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import InterviewUpload from "@/components/InterviewUpload";
import MemoManager from "@/components/MemoManager";
import CodeExplorer from "@/components/CodeExplorer";
import TheoryViewer from "@/components/TheoryViewer";

const DOMAIN_TEMPLATES = ["generic", "education", "ngo", "government", "market_research"] as const;
type DomainTemplate = typeof DOMAIN_TEMPLATES[number];

function isDomainTemplate(value: string): value is DomainTemplate {
    return (DOMAIN_TEMPLATES as readonly string[]).includes(value);
}

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
    const [taskProgress, setTaskProgress] = useState<number | null>(null);
    const [taskStep, setTaskStep] = useState<string>("");
    const [theoryDone, setTheoryDone] = useState(false);
    const [theoryFailed, setTheoryFailed] = useState(false);
    const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
    const [logLines, setLogLines] = useState<string[]>([]);
    const prevStepRef = useRef<string>("");
    const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

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

    // Restore in-progress task_id from localStorage after page reload
    useEffect(() => {
        if (!selectedProjectId || !isAuthenticated) return;
        setCurrentTaskId(null);
        const saved = localStorage.getItem(`theory_task_${selectedProjectId}`);
        if (!saved) return;
        try {
            const { task_id, timestamp } = JSON.parse(saved);
            if (Date.now() - timestamp > 30 * 60 * 1000) {
                localStorage.removeItem(`theory_task_${selectedProjectId}`);
            } else {
                setCurrentTaskId(task_id);
            }
        } catch {
            localStorage.removeItem(`theory_task_${selectedProjectId}`);
        }
    }, [selectedProjectId, isAuthenticated]);

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
        const templateInput = prompt(
            "Plantilla de dominio (generic, education, ngo, government, market_research):",
            "generic"
        );
        if (templateInput === null) return;
        const domainTemplate = templateInput.trim().toLowerCase() || "generic";
        if (!isDomainTemplate(domainTemplate)) {
            alert("Plantilla no válida. Usa: generic, education, ngo, government, market_research.");
            return;
        }

        try {
            const { apiClient } = await import("@/lib/api");
            const response = await apiClient("/projects/", {
                method: "POST",
                body: JSON.stringify({
                    name,
                    description: "Proyecto de investigación",
                    methodological_profile: "constructivist",
                    domain_template: domainTemplate,
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

    async function handleEditProject() {
        if (!selectedProjectId || !selectedProject) return;

        const nameInput = prompt("Nuevo nombre del proyecto:", selectedProject.name || "");
        if (nameInput === null) return;
        const name = nameInput.trim();
        if (!name) {
            alert("El nombre no puede estar vacio.");
            return;
        }

        const templateInput = prompt(
            "Plantilla de dominio (generic, education, ngo, government, market_research):",
            selectedProject.domain_template || "generic"
        );
        if (templateInput === null) return;
        const domainTemplate = templateInput.trim().toLowerCase() || "generic";
        if (!isDomainTemplate(domainTemplate)) {
            alert("Plantilla no valida. Usa: generic, education, ngo, government, market_research.");
            return;
        }

        const descriptionInput = prompt("Descripcion del proyecto:", selectedProject.description || "");
        if (descriptionInput === null) return;

        try {
            const { apiClient } = await import("@/lib/api");
            const response = await apiClient(`/projects/${selectedProjectId}`, {
                method: "PATCH",
                body: JSON.stringify({
                    name,
                    description: descriptionInput,
                    domain_template: domainTemplate,
                }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                alert(`Error al actualizar proyecto: ${errData.detail || response.statusText}`);
                return;
            }

            const updatedProject = await response.json();
            setProjects((prev) => prev.map((p) => (p.id === updatedProject.id ? updatedProject : p)));
        } catch (error) {
            console.error("Project update error:", error);
            alert("Error de conexion al actualizar proyecto");
        }
    }

    const STEP_DISPLAY: Record<string, string> = {
        queued:        "En cola...",
        pipeline_start:"Iniciando pipeline...",
        load_project:  "Cargando proyecto...",
        load_categories: "Cargando categorías...",
        auto_code:     "Auto-codificando entrevistas...",
        neo4j_taxonomy_sync: "Sincronizando taxonomía en Neo4j...",
        network_metrics: "Calculando métricas de red...",
        semantic_evidence: "Recuperando evidencia semántica...",
        identify_central_category: "Identificando categoría central...",
        build_straussian_paradigm: "Construyendo paradigma...",
        analyze_saturation_and_gaps: "Analizando brechas y saturación...",
        save_theory:   "Guardando teoría...",
        coding:        "Codificando fragmentos de entrevistas...",
        coding_done:   "Codificación completada",
        embeddings:    "Generando embeddings semánticos...",
        neo4j:         "Sincronizando grafo de conocimiento...",
        theory_engine: "Construyendo teoría fundada...",
        categories:    "Analizando categorías emergentes...",
        saturation:    "Verificando saturación teórica...",
        saving:        "Guardando teoría en base de datos...",
        completed:     "Teoría completada",
        failed:        "Pipeline terminado con error",
    };

    function handleExportTheory() {
        if (!activeTheory) return;
        const blob = new Blob([JSON.stringify(activeTheory, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `teoria-${selectedProjectId}-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    async function handleGenerateTheory() {
        if (!selectedProjectId || generatingTheory) return;

        setGeneratingTheory(true);
        setTheoryDone(false);
        setTheoryFailed(false);
        setTaskProgress(0);
        setTaskStep("");
        setTheoryMessage("");
        setLogLines([]);
        prevStepRef.current = "";

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
            setCurrentTaskId(task_id);
            localStorage.setItem(
                `theory_task_${selectedProjectId}`,
                JSON.stringify({ task_id, timestamp: Date.now() })
            );

            // 2. Poll with adaptive delay until completed or failed (max 10 min)
            let attempts = 0;
            const maxAttempts = 120;
            let nextDelayMs = Math.max(2000, (enqueueData.next_poll_seconds || 5) * 1000);

            const poll = async () => {
                attempts++;
                try {
                    const statusResp = await apiClient(
                        `/projects/${selectedProjectId}/generate-theory/status/${task_id}`
                    );
                    if (!statusResp.ok) {
                        setTheoryFailed(true);
                        setTheoryMessage("Error al consultar estado de la tarea.");
                        setGeneratingTheory(false);
                        return;
                    }
                    const taskData = await statusResp.json();
                    nextDelayMs = Math.max(2000, (taskData.next_poll_seconds || 5) * 1000);

                    if (typeof taskData.progress === "number") setTaskProgress(taskData.progress);
                    if (taskData.step) {
                        setTaskStep(taskData.step);
                        if (taskData.step !== prevStepRef.current) {
                            prevStepRef.current = taskData.step;
                            const ts = new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                            setLogLines(prev => [...prev.slice(-30), `${ts}  ${STEP_DISPLAY[taskData.step] || taskData.step}`]);
                        }
                    }

                    if (taskData.status === "completed") {
                        setActiveTheory(taskData.result);
                        setTaskProgress(100);
                        setTheoryDone(true);
                        setGeneratingTheory(false);
                        localStorage.removeItem(`theory_task_${selectedProjectId}`);
                        return;
                    }
                    if (taskData.status === "failed") {
                        const errMsg = taskData.error || "La generación falló.";
                        setTheoryFailed(true);
                        setTheoryMessage(errMsg);
                        const ts = new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                        setLogLines(prev => [...prev.slice(-30), `${ts}  ERROR: ${errMsg}`]);
                        setGeneratingTheory(false);
                        localStorage.removeItem(`theory_task_${selectedProjectId}`);
                        return;
                    }
                    if (attempts >= maxAttempts) {
                        setTheoryFailed(true);
                        setTheoryMessage("Tiempo de espera agotado (10 min). El proceso continúa en segundo plano.");
                        setGeneratingTheory(false);
                        return;
                    }

                    // Gentle backoff to reduce backend pressure on long jobs.
                    if (attempts > 12) {
                        nextDelayMs = Math.min(15000, Math.round(nextDelayMs * 1.15));
                    }
                    setTimeout(poll, nextDelayMs);
                } catch {
                    setTheoryFailed(true);
                    setTheoryMessage("Error de conexión al consultar estado.");
                    setGeneratingTheory(false);
                }
            };
            setTimeout(poll, nextDelayMs);

        } catch (error) {
            console.error("Error generating theory:", error);
            setTheoryFailed(true);
            setTheoryMessage("Error de conexión al generar teoría.");
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
                            onClick={handleEditProject}
                            disabled={!selectedProjectId}
                            className="rounded-2xl border border-zinc-200 px-6 py-2 text-sm font-bold hover:bg-zinc-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed dark:border-zinc-800 dark:text-white"
                        >
                            Editar Proyecto
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
                                    <div id="theory-viewer" className="col-span-2 mt-8">
                                        <TheoryViewer projectId={selectedProjectId!} theory={activeTheory} />
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

                                        <div className="rounded-3xl bg-indigo-600 p-8 text-white shadow-xl shadow-indigo-500/20">
                                            <h4 className="font-bold mb-2 text-lg">Teorización Assist</h4>

                                            {/* Idle */}
                                            {!generatingTheory && !theoryDone && !theoryFailed && (
                                                <>
                                                    <p className="text-white/80 text-sm mb-6">
                                                        {activeTheory
                                                            ? "Teoría anterior disponible. Puedes regenerarla con los datos actuales."
                                                            : "Analiza los datos del proyecto para buscar patrones emergentes."}
                                                    </p>
                                                    {activeTheory && (
                                                        <div className="flex gap-2 mb-3">
                                                            <button
                                                                onClick={() => setTimeout(() => document.getElementById("theory-viewer")?.scrollIntoView({ behavior: "smooth" }), 50)}
                                                                className="flex-1 rounded-xl bg-white py-2.5 text-sm font-bold text-indigo-600 hover:bg-indigo-50 transition-all"
                                                            >
                                                                Ver Teoría
                                                            </button>
                                                            <button
                                                                onClick={handleExportTheory}
                                                                className="flex-1 rounded-xl border border-white/40 py-2.5 text-sm font-bold text-white hover:bg-white/10 transition-all"
                                                            >
                                                                Exportar JSON
                                                            </button>
                                                        </div>
                                                    )}
                                                    <button
                                                        className="w-full rounded-xl bg-white py-3 text-sm font-bold text-indigo-600 shadow-lg transition-all hover:bg-indigo-50 active:scale-98"
                                                        onClick={handleGenerateTheory}
                                                    >
                                                        {activeTheory ? "Regenerar Teoría" : "Generar Teoría (v1.2)"}
                                                    </button>
                                                </>
                                            )}

                                            {/* Generating — progress bar */}
                                            {generatingTheory && (
                                                <div>
                                                    <p className="text-white/80 text-sm mb-3">
                                                        {STEP_DISPLAY[taskStep] || "Procesando datos..."}
                                                    </p>
                                                    <div className="mb-3">
                                                        <div className="flex justify-between text-xs font-semibold text-white/70 mb-1">
                                                            <span>{taskStep || "iniciando"}</span>
                                                            <span>{taskProgress ?? 0}%</span>
                                                        </div>
                                                        <div className="h-2 w-full rounded-full bg-white/20 overflow-hidden">
                                                            <div
                                                                className="h-full rounded-full bg-white transition-all duration-700 ease-out"
                                                                style={{ width: `${taskProgress ?? 0}%` }}
                                                            />
                                                        </div>
                                                    </div>
                                                    {currentTaskId && (
                                                        <p className="text-xs text-white/40 font-mono truncate">
                                                            task: {currentTaskId}
                                                        </p>
                                                    )}
                                                    {logLines.length > 0 && (
                                                        <div className="mt-2 bg-black/30 rounded-lg p-2 max-h-20 overflow-y-auto">
                                                            {logLines.slice(-5).map((line, i) => (
                                                                <p key={i} className="text-xs font-mono text-white/55 leading-relaxed">{line}</p>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Done */}
                                            {theoryDone && (
                                                <div>
                                                    <p className="text-white/90 text-sm mb-4">
                                                        ✅ Teoría generada. Lista para revisar y exportar.
                                                    </p>
                                                    <div className="flex gap-2 mb-2">
                                                        <button
                                                            onClick={() => setTimeout(() => document.getElementById("theory-viewer")?.scrollIntoView({ behavior: "smooth" }), 50)}
                                                            className="flex-1 rounded-xl bg-white py-2.5 text-sm font-bold text-indigo-600 hover:bg-indigo-50 transition-all"
                                                        >
                                                            Ver Teoría
                                                        </button>
                                                        <button
                                                            onClick={handleExportTheory}
                                                            className="flex-1 rounded-xl border border-white/40 py-2.5 text-sm font-bold text-white hover:bg-white/10 transition-all"
                                                        >
                                                            Exportar JSON
                                                        </button>
                                                    </div>
                                                    <button
                                                        onClick={() => { setTheoryDone(false); setTaskProgress(null); setTaskStep(""); }}
                                                        className="w-full text-xs text-white/40 hover:text-white/70 transition-colors py-1"
                                                    >
                                                        Regenerar
                                                    </button>
                                                </div>
                                            )}

                                            {/* Failed */}
                                            {theoryFailed && (
                                                <div>
                                                    <p className="text-white font-semibold text-sm mb-2">La generación falló.</p>
                                                    {theoryMessage && (
                                                        <div className="mb-3 bg-black/30 rounded-lg p-2 max-h-28 overflow-y-auto">
                                                            <p className="text-xs font-mono text-red-200 break-all leading-relaxed whitespace-pre-wrap">{theoryMessage}</p>
                                                        </div>
                                                    )}
                                                    <button
                                                        onClick={() => { setTheoryFailed(false); setTheoryMessage(""); setTaskProgress(null); setTaskStep(""); setLogLines([]); handleGenerateTheory(); }}
                                                        className="w-full rounded-xl bg-white py-3 text-sm font-bold text-indigo-600 hover:bg-indigo-50 transition-all"
                                                    >
                                                        Reintentar
                                                    </button>
                                                </div>
                                            )}
                                        </div>
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






