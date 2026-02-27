"use client";

import { useMsal, useIsAuthenticated } from "@azure/msal-react";
import { getGoogleToken } from "@/lib/googleAuth";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import InterviewUpload from "@/components/InterviewUpload";
import MemoManager from "@/components/MemoManager";
import CodeExplorer from "@/components/CodeExplorer";
import TheoryViewer from "@/components/TheoryViewer";
import type { Theory as TheoryViewerTheory } from "@/components/TheoryViewer";
import InterviewModal from "@/components/InterviewModal";
import ExportPanel, { enqueueLocalExport } from "@/components/ExportPanel";
import AuthenticatedChatbot from "@/components/assistant/AuthenticatedChatbot";

const DOMAIN_TEMPLATES = ["generic", "education", "ngo", "government", "market_research"] as const;
type DomainTemplate = typeof DOMAIN_TEMPLATES[number];
type DashboardTab = "overview" | "codes" | "interviews" | "memos";
type TheoryViewerStateSnapshot = {
    sectionFilter: string;
    claimTypeFilter: string;
    page: number;
    expanded: Record<string, boolean>;
};
const THEORY_VIEWER_STATE_STORAGE_KEY = "theory_viewer_state_v1";
const DASHBOARD_UI_STATE_STORAGE_KEY = "dashboard_ui_state_v1";

type DashboardUiStateSnapshot = {
    selectedProjectId: string | null;
    activeTab: DashboardTab;
};
type ResetUiAction = "active_theory" | "dashboard_ui" | "all";

type SegmentPreset = {
    label: string;
    domainTemplate: DomainTemplate;
    suggestedName: string;
    suggestedDescription: string;
};

type CreateProjectFormState = {
    name: string;
    domainTemplate: DomainTemplate;
    description: string;
};

type ProjectSummary = {
    id: string;
    name?: string;
    description?: string;
    domain_template?: string;
    saturation_score?: number;
    [key: string]: unknown;
};

type InterviewSummary = {
    id: string;
    participant_pseudonym?: string;
    transcription_method?: string;
    word_count?: number;
    language?: string;
    status?: string;
    [key: string]: unknown;
};

type TheorySummary = TheoryViewerTheory & { status?: string };

const SEGMENT_PRESETS: Record<string, SegmentPreset> = {
    educacion: {
        label: "Educación",
        domainTemplate: "education",
        suggestedName: "Piloto Educación",
        suggestedDescription: "Proyecto enfocado en experiencia educativa y engagement con apoderados.",
    },
    ong: {
        label: "ONG",
        domainTemplate: "ngo",
        suggestedName: "Piloto ONG",
        suggestedDescription: "Proyecto para entender necesidades comunitarias y evidenciar impacto para donantes.",
    },
    "market-research": {
        label: "Estudio de Mercado",
        domainTemplate: "market_research",
        suggestedName: "Piloto Estudio de Mercado",
        suggestedDescription: "Proyecto para acelerar análisis cualitativo y mejorar margen operativo.",
    },
    b2c: {
        label: "B2C",
        domainTemplate: "generic",
        suggestedName: "Piloto B2C",
        suggestedDescription: "Proyecto para mejorar servicio al cliente y fortalecer retención.",
    },
    consultoria: {
        label: "Consultoría",
        domainTemplate: "generic",
        suggestedName: "Piloto Consultoría",
        suggestedDescription: "Proyecto para diferenciar entregables y acelerar tiempos de entrega.",
    },
    "sector-publico": {
        label: "Sector Público",
        domainTemplate: "government",
        suggestedName: "Piloto Sector Público",
        suggestedDescription: "Proyecto para participación ciudadana y transparencia institucional.",
    },
};

function isSameExpandedState(a: Record<string, boolean>, b: Record<string, boolean>): boolean {
    const aKeys = Object.keys(a || {});
    const bKeys = Object.keys(b || {});
    if (aKeys.length !== bKeys.length) return false;
    for (const key of aKeys) {
        if ((a || {})[key] !== (b || {})[key]) return false;
    }
    return true;
}

function isDomainTemplate(value: string): value is DomainTemplate {
    return (DOMAIN_TEMPLATES as readonly string[]).includes(value);
}

function isDashboardTab(value: string): value is DashboardTab {
    return value === "overview" || value === "codes" || value === "interviews" || value === "memos";
}

export default function Dashboard() {
    const { inProgress } = useMsal();
    const msalIsAuthenticated = useIsAuthenticated();
    const [googleAuth, setGoogleAuth] = useState(false);
    const isAuthenticated = msalIsAuthenticated || googleAuth;
    const router = useRouter();
    const searchParams = useSearchParams();
    const segmentKey = (searchParams.get("segment") || "").toLowerCase();
    const segmentPreset = SEGMENT_PRESETS[segmentKey] || null;

    useEffect(() => {
        setGoogleAuth(!!getGoogleToken());
    }, []);

    useEffect(() => {
        // Only redirect if MSAL is done processing, no MSAL account, and no Google token
        if (inProgress === "none" && !isAuthenticated && !getGoogleToken()) {
            console.log("[Dashboard] Not authenticated, redirecting to /login/");
            router.replace("/login/");
        }
    }, [inProgress, isAuthenticated, router]);

    const [projects, setProjects] = useState<ProjectSummary[]>([]);
    const [loadingProjects, setLoadingProjects] = useState(true);
    const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<DashboardTab>("overview");

    // Interviews tab state
    const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
    const [loadingInterviews, setLoadingInterviews] = useState(false);
    const [openInterviewId, setOpenInterviewId] = useState<string | null>(null);

    const [activeTheory, setActiveTheory] = useState<TheorySummary | null>(null);
    const [generatingTheory, setGeneratingTheory] = useState(false);
    const [theoryMessage, setTheoryMessage] = useState("");
    const [taskProgress, setTaskProgress] = useState<number | null>(null);
    const [taskStep, setTaskStep] = useState<string>("");
    const [theoryDone, setTheoryDone] = useState(false);
    const [theoryFailed, setTheoryFailed] = useState(false);
    const [showResetUiModal, setShowResetUiModal] = useState(false);
    const [showCreateProjectModal, setShowCreateProjectModal] = useState(false);
    const [showEditProjectModal, setShowEditProjectModal] = useState(false);
    const [creatingProject, setCreatingProject] = useState(false);
    const [createProjectError, setCreateProjectError] = useState<string | null>(null);
    const [editingProject, setEditingProject] = useState(false);
    const [editProjectError, setEditProjectError] = useState<string | null>(null);
    const [createProjectForm, setCreateProjectForm] = useState<CreateProjectFormState>({
        name: "",
        domainTemplate: "generic",
        description: "Proyecto de investigación",
    });
    const [editProjectForm, setEditProjectForm] = useState<CreateProjectFormState>({
        name: "",
        domainTemplate: "generic",
        description: "",
    });
    const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
    const [logLines, setLogLines] = useState<string[]>([]);
    const [theoryViewerStateByTheory, setTheoryViewerStateByTheory] = useState<Record<string, TheoryViewerStateSnapshot>>({});
    const prevStepRef = useRef<string>("");
    const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;
    const activeTheoryViewerState =
        activeTheory?.id && theoryViewerStateByTheory[activeTheory.id]
            ? theoryViewerStateByTheory[activeTheory.id]
            : undefined;

    function resetDashboardUiState() {
        setActiveTab("overview");
        setSelectedProjectId(null);
        setOpenInterviewId(null);
        setTheoryDone(false);
        setTheoryFailed(false);
        setTaskProgress(null);
        setTaskStep("");
        setTheoryMessage("");
        setLogLines([]);
        setCurrentTaskId(null);
        try {
            localStorage.removeItem(DASHBOARD_UI_STATE_STORAGE_KEY);
        } catch {
            // noop
        }
    }

    function resetTheoryViewerState(scope: "active_theory" | "all") {
        if (!Object.keys(theoryViewerStateByTheory).length) return;
        setTheoryViewerStateByTheory((prev) => {
            if (scope === "all") {
                return {};
            }
            if (scope === "active_theory") {
                if (!activeTheory?.id) return prev;
                const next = { ...prev };
                delete next[activeTheory.id];
                return next;
            }
            return prev;
        });
    }

    function handleResetUiAction(action: ResetUiAction) {
        if (action === "active_theory") {
            resetTheoryViewerState("active_theory");
        } else if (action === "dashboard_ui") {
            resetDashboardUiState();
        } else {
            resetTheoryViewerState("all");
            resetDashboardUiState();
        }
        setShowResetUiModal(false);
    }

    useEffect(() => {
        try {
            const raw = localStorage.getItem(THEORY_VIEWER_STATE_STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw) as Record<string, Partial<TheoryViewerStateSnapshot>>;
            if (parsed && typeof parsed === "object") {
                const normalized: Record<string, TheoryViewerStateSnapshot> = {};
                for (const [theoryId, state] of Object.entries(parsed)) {
                    normalized[theoryId] = {
                        sectionFilter: state?.sectionFilter || "all",
                        claimTypeFilter: state?.claimTypeFilter || "all",
                        page: typeof state?.page === "number" ? state.page : 0,
                        expanded: (state?.expanded && typeof state.expanded === "object") ? state.expanded : {},
                    };
                }
                setTheoryViewerStateByTheory(normalized);
            }
        } catch {
            localStorage.removeItem(THEORY_VIEWER_STATE_STORAGE_KEY);
        }
    }, []);

    useEffect(() => {
        try {
            localStorage.setItem(THEORY_VIEWER_STATE_STORAGE_KEY, JSON.stringify(theoryViewerStateByTheory));
        } catch {
            // noop
        }
    }, [theoryViewerStateByTheory]);

    useEffect(() => {
        try {
            const raw = localStorage.getItem(DASHBOARD_UI_STATE_STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw) as Partial<DashboardUiStateSnapshot>;
            if (parsed && typeof parsed === "object") {
                if (typeof parsed.selectedProjectId === "string" || parsed.selectedProjectId === null) {
                    setSelectedProjectId(parsed.selectedProjectId ?? null);
                }
                if (typeof parsed.activeTab === "string" && isDashboardTab(parsed.activeTab)) {
                    setActiveTab(parsed.activeTab);
                }
            }
        } catch {
            localStorage.removeItem(DASHBOARD_UI_STATE_STORAGE_KEY);
        }
    }, []);

    useEffect(() => {
        const snapshot: DashboardUiStateSnapshot = {
            selectedProjectId,
            activeTab,
        };
        try {
            localStorage.setItem(DASHBOARD_UI_STATE_STORAGE_KEY, JSON.stringify(snapshot));
        } catch {
            // noop
        }
    }, [selectedProjectId, activeTab]);

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

            try {
                const { apiClient } = await import("@/lib/api");
                const response = await apiClient(`/projects/${selectedProjectId}/theories`);

                if (response.ok) {
                    const theories = (await response.json()) as TheorySummary[];
                    // Assuming we want the latest completed theory
                    const latest = theories.find((t) => t.status === "completed" || t.status === "draft");
                    setActiveTheory(latest || null);
                }
            } catch (error) {
                console.error("Error fetching theory:", error);
            }
        }

        fetchTheory();
    }, [selectedProjectId]);

    // Load interviews when tab is selected
    useEffect(() => {
        if (activeTab !== "interviews" || !selectedProjectId || !isAuthenticated) return;
        setLoadingInterviews(true);
        const load = async () => {
            try {
                const { apiClient } = await import("@/lib/api");
                const resp = await apiClient(`/interviews/project/${selectedProjectId}`);
                if (resp.ok) setInterviews(await resp.json());
            } catch (e) {
                console.error("Error loading interviews:", e);
            } finally {
                setLoadingInterviews(false);
            }
        };
        load();
    }, [activeTab, selectedProjectId, isAuthenticated]);

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

    function openCreateProjectModal(preset?: SegmentPreset | null) {
        const selectedPreset = preset || segmentPreset;
        setCreateProjectError(null);
        setCreateProjectForm({
            name: selectedPreset?.suggestedName || "",
            domainTemplate: selectedPreset?.domainTemplate || "generic",
            description: selectedPreset?.suggestedDescription || "Proyecto de investigación",
        });
        setShowCreateProjectModal(true);
    }

    async function handleCreateProjectSubmit() {
        const name = createProjectForm.name.trim();
        if (!name) {
            setCreateProjectError("El nombre del proyecto es obligatorio.");
            return;
        }

        try {
            setCreatingProject(true);
            setCreateProjectError(null);
            const { apiClient } = await import("@/lib/api");
            const response = await apiClient("/projects/", {
                method: "POST",
                body: JSON.stringify({
                    name,
                    description: createProjectForm.description.trim() || "Proyecto de investigación",
                    methodological_profile: "constructivist",
                    domain_template: createProjectForm.domainTemplate,
                    language: "es"
                })
            });

            if (response.ok) {
                const newProj = await response.json();
                setProjects(prev => [newProj, ...prev]);
                setSelectedProjectId(newProj.id);
                setShowCreateProjectModal(false);
            } else {
                const errData = await response.json().catch(() => ({}));
                setCreateProjectError(errData.detail || response.statusText || "No se pudo crear el proyecto.");
            }
        } catch (error) {
            console.error("Creation error:", error);
            setCreateProjectError("Error de conexión al crear proyecto.");
        } finally {
            setCreatingProject(false);
        }
    }

    function openEditProjectModal() {
        if (!selectedProject) return;
        const selectedDomainTemplate = selectedProject.domain_template || "";
        setEditProjectError(null);
        setEditProjectForm({
            name: selectedProject.name || "",
            domainTemplate: isDomainTemplate(selectedDomainTemplate)
                ? selectedDomainTemplate
                : "generic",
            description: selectedProject.description || "",
        });
        setShowEditProjectModal(true);
    }

    async function handleEditProjectSubmit() {
        if (!selectedProjectId) return;
        const name = editProjectForm.name.trim();
        if (!name) {
            setEditProjectError("El nombre del proyecto es obligatorio.");
            return;
        }
        try {
            setEditingProject(true);
            setEditProjectError(null);
            const { apiClient } = await import("@/lib/api");
            const response = await apiClient(`/projects/${selectedProjectId}`, {
                method: "PATCH",
                body: JSON.stringify({
                    name,
                    description: editProjectForm.description.trim(),
                    domain_template: editProjectForm.domainTemplate,
                }),
            });
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                setEditProjectError(errData.detail || response.statusText || "No se pudo actualizar el proyecto.");
                return;
            }
            const updatedProject = await response.json();
            setProjects((prev) => prev.map((p) => (p.id === updatedProject.id ? updatedProject : p)));
            setShowEditProjectModal(false);
        } catch (error) {
            console.error("Project update error:", error);
            setEditProjectError("Error de conexión al actualizar proyecto.");
        } finally {
            setEditingProject(false);
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
                } catch (pollErr) {
                    console.error("[poll] network exception (attempt", attempts, "):", pollErr);
                    // Retry up to 5 times on transient network/MSAL errors before giving up
                    if (attempts < 5) {
                        const retryDelay = Math.min(nextDelayMs * 2, 15000);
                        setTimeout(poll, retryDelay);
                    } else {
                        setTheoryFailed(true);
                        setTheoryMessage("Error de conexión al consultar estado. Intenta refrescar la página.");
                        setGeneratingTheory(false);
                    }
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
                        onClick={() => setActiveTab("interviews")}
                        disabled={!selectedProjectId}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'interviews' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'} ${!selectedProjectId ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        🎙️ Entrevistas
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
                <header className="border-b border-zinc-100 bg-white/50 p-8 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-950/50">
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <h1 className="text-2xl font-bold dark:text-white">
                                {activeTab === "overview" && "Panel de Control"}
                                {activeTab === "codes" && "Exploración de Conceptos"}
                                {activeTab === "interviews" && "Entrevistas"}
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
                            onClick={openEditProjectModal}
                            disabled={!selectedProjectId}
                            className="rounded-2xl border border-zinc-200 px-6 py-2 text-sm font-bold hover:bg-zinc-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed dark:border-zinc-800 dark:text-white"
                        >
                                Editar Proyecto
                            </button>
                            <button
                                onClick={() => openCreateProjectModal()}
                                className="rounded-2xl bg-indigo-600 px-6 py-2 text-sm font-bold text-white hover:bg-indigo-700 transition-all"
                            >
                                + Nuevo Proyecto
                            </button>
                            <button
                                onClick={() => setShowResetUiModal(true)}
                                className="rounded-2xl border border-amber-300 px-4 py-2 text-xs font-bold text-amber-700 hover:bg-amber-50 transition-all"
                                title="Limpiar estado persistido de la UI"
                            >
                                Reset UI
                            </button>
                        </div>
                    </div>
                    {segmentPreset && (
                        <div className="mt-4 rounded-2xl border border-indigo-200 bg-indigo-50/70 px-4 py-3 dark:border-indigo-900/60 dark:bg-indigo-950/40">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <p className="text-sm text-indigo-800 dark:text-indigo-300">
                                    Contexto aplicado: <span className="font-semibold">{segmentPreset.label}</span>.
                                    Puedes iniciar un proyecto con plantilla y descripción sugeridas.
                                </p>
                                <button
                                    onClick={() => openCreateProjectModal(segmentPreset)}
                                    className="rounded-xl border border-indigo-300 bg-white px-3 py-1.5 text-xs font-bold text-indigo-700 hover:bg-indigo-100 dark:border-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-200 dark:hover:bg-indigo-900/60"
                                >
                                    Crear proyecto sugerido
                                </button>
                            </div>
                        </div>
                    )}
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
                                            onClick={() => openCreateProjectModal(segmentPreset)}
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
                                        <TheoryViewer
                                            projectId={selectedProjectId!}
                                            theory={activeTheory}
                                            viewerState={activeTheoryViewerState}
                                            onViewerStateChange={(state) => {
                                                if (!activeTheory?.id) return;
                                                setTheoryViewerStateByTheory((prev) => {
                                                    const current = prev[activeTheory.id];
                                                    if (
                                                        current &&
                                                        current.sectionFilter === state.sectionFilter &&
                                                        current.claimTypeFilter === state.claimTypeFilter &&
                                                        current.page === state.page &&
                                                        isSameExpandedState(current.expanded, state.expanded)
                                                    ) {
                                                        return prev;
                                                    }
                                                    return {
                                                        ...prev,
                                                        [activeTheory.id]: state,
                                                    };
                                                });
                                            }}
                                        />
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
                                                        <progress
                                                            className="h-2 w-full overflow-hidden rounded-full"
                                                            max={100}
                                                            value={taskProgress ?? 0}
                                                            aria-label="Progreso de generación de teoría"
                                                        />
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

                    {activeTab === "interviews" && selectedProjectId && (
                        <div className="max-w-5xl mx-auto space-y-6">
                            <div className="rounded-3xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-zinc-900/50">
                                <div className="flex items-center justify-between mb-6">
                                    <h3 className="text-xl font-bold dark:text-white">🎙️ Entrevistas del Proyecto</h3>
                                    <span className="text-sm text-zinc-500 font-medium">{interviews.length} entrevista{interviews.length !== 1 ? 's' : ''}</span>
                                </div>
                                {loadingInterviews ? (
                                    <p className="text-zinc-500 text-sm">Cargando entrevistas...</p>
                                ) : interviews.length === 0 ? (
                                    <p className="text-sm text-zinc-400">No hay entrevistas en este proyecto. Sube una desde el Panel de Control.</p>
                                ) : (
                                    <div className="space-y-3">
                                        {interviews.map((iv) => (
                                            <div key={iv.id} className="group flex items-center justify-between rounded-xl border border-zinc-100 p-4 hover:bg-zinc-50 transition-all dark:border-zinc-800 dark:hover:bg-zinc-900">
                                                <div className="min-w-0">
                                                    <h4 className="font-bold text-sm dark:text-white truncate">{iv.participant_pseudonym || iv.id}</h4>
                                                    <p className="text-xs text-zinc-500">
                                                        {iv.transcription_method || 'sin transcripción'}
                                                        {iv.word_count ? ` · ${iv.word_count} palabras` : ''}
                                                        {iv.language ? ` · ${iv.language}` : ''}
                                                    </p>
                                                </div>
                                                <div className="flex gap-2 ml-4">
                                                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                                                        iv.status === 'transcribed' ? 'bg-green-100 text-green-700' :
                                                        iv.status === 'processing' ? 'bg-yellow-100 text-yellow-700' :
                                                        'bg-zinc-100 text-zinc-500'
                                                    }`}>{iv.status || 'uploaded'}</span>
                                                    <button
                                                        onClick={() => setOpenInterviewId(iv.id)}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-xs font-bold text-indigo-600 border border-indigo-200 rounded-lg px-3 py-1"
                                                    >
                                                        Ver transcripción
                                                    </button>
                                                    <button
                                                        onClick={async () => {
                                                            const { apiClient } = await import('@/lib/api');
                                                            const resp = await apiClient('interviews/export', {
                                                                method: 'POST',
                                                                body: JSON.stringify({
                                                                    project_id: selectedProjectId,
                                                                    interview_ids: [iv.id],
                                                                    scope: 'selected',
                                                                    format: 'json',
                                                                    include_metadata: true,
                                                                    include_codes: true,
                                                                    include_timestamps: true,
                                                                    language: 'es',
                                                                }),
                                                            });
                                                            if (resp.ok) {
                                                                const d = await resp.json();
                                                                enqueueLocalExport(d.task_id);
                                                            }
                                                        }}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-xs font-bold text-zinc-600 border border-zinc-200 rounded-lg px-3 py-1"
                                                    >
                                                        Exportar JSON
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <ExportPanel projectId={selectedProjectId} />
                        </div>
                    )}

                    {activeTab === "memos" && selectedProjectId && (
                        <div className="max-w-4xl mx-auto">
                            <MemoManager projectId={selectedProjectId} />
                        </div>
                    )}
                </div>
            </main>

            {openInterviewId && (
                <InterviewModal
                    interviewId={openInterviewId}
                    projectId={selectedProjectId}
                    onClose={() => setOpenInterviewId(null)}
                />
            )}

            {showCreateProjectModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
                    <div className="w-full max-w-lg rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900">
                        <h3 className="text-lg font-bold dark:text-white">Crear nuevo proyecto</h3>
                        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
                            Configura el proyecto inicial para comenzar tu prueba gratuita.
                        </p>
                        <div className="mt-5 space-y-4">
                            <div>
                                <label htmlFor="create-project-name" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Nombre</label>
                                <input
                                    id="create-project-name"
                                    value={createProjectForm.name}
                                    onChange={(event) => setCreateProjectForm((prev) => ({ ...prev, name: event.target.value }))}
                                    className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
                                    placeholder="Ej: Piloto ONG"
                                />
                            </div>
                            <div>
                                <label htmlFor="create-project-domain-template" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Plantilla de dominio</label>
                                <select
                                    id="create-project-domain-template"
                                    value={createProjectForm.domainTemplate}
                                    onChange={(event) => {
                                        const nextValue = event.target.value;
                                        if (!isDomainTemplate(nextValue)) return;
                                        setCreateProjectForm((prev) => ({ ...prev, domainTemplate: nextValue }));
                                    }}
                                    className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
                                >
                                    <option value="generic">generic</option>
                                    <option value="education">education</option>
                                    <option value="ngo">ngo</option>
                                    <option value="government">government</option>
                                    <option value="market_research">market_research</option>
                                </select>
                            </div>
                            <div>
                                <label htmlFor="create-project-description" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Descripción</label>
                                <textarea
                                    id="create-project-description"
                                    value={createProjectForm.description}
                                    onChange={(event) => setCreateProjectForm((prev) => ({ ...prev, description: event.target.value }))}
                                    className="min-h-24 w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
                                    placeholder="Describe brevemente el objetivo del proyecto."
                                />
                            </div>
                            {createProjectError && (
                                <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                                    {createProjectError}
                                </div>
                            )}
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button
                                onClick={() => setShowCreateProjectModal(false)}
                                className="rounded-xl border border-zinc-200 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:text-white dark:hover:bg-zinc-800"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleCreateProjectSubmit}
                                disabled={creatingProject}
                                className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-60"
                            >
                                {creatingProject ? "Creando..." : "Crear proyecto"}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {showEditProjectModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
                    <div className="w-full max-w-lg rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900">
                        <h3 className="text-lg font-bold dark:text-white">Editar proyecto</h3>
                        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
                            Actualiza nombre, plantilla y descripción del proyecto.
                        </p>
                        <div className="mt-5 space-y-4">
                            <div>
                                <label htmlFor="edit-project-name" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Nombre</label>
                                <input
                                    id="edit-project-name"
                                    value={editProjectForm.name}
                                    onChange={(event) => setEditProjectForm((prev) => ({ ...prev, name: event.target.value }))}
                                    className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
                                />
                            </div>
                            <div>
                                <label htmlFor="edit-project-domain-template" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Plantilla de dominio</label>
                                <select
                                    id="edit-project-domain-template"
                                    value={editProjectForm.domainTemplate}
                                    onChange={(event) => {
                                        const nextValue = event.target.value;
                                        if (!isDomainTemplate(nextValue)) return;
                                        setEditProjectForm((prev) => ({ ...prev, domainTemplate: nextValue }));
                                    }}
                                    className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
                                >
                                    <option value="generic">generic</option>
                                    <option value="education">education</option>
                                    <option value="ngo">ngo</option>
                                    <option value="government">government</option>
                                    <option value="market_research">market_research</option>
                                </select>
                            </div>
                            <div>
                                <label htmlFor="edit-project-description" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-zinc-500">Descripción</label>
                                <textarea
                                    id="edit-project-description"
                                    value={editProjectForm.description}
                                    onChange={(event) => setEditProjectForm((prev) => ({ ...prev, description: event.target.value }))}
                                    className="min-h-24 w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
                                />
                            </div>
                            {editProjectError && (
                                <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                                    {editProjectError}
                                </div>
                            )}
                        </div>
                        <div className="mt-6 flex justify-end gap-3">
                            <button
                                onClick={() => setShowEditProjectModal(false)}
                                className="rounded-xl border border-zinc-200 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:text-white dark:hover:bg-zinc-800"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleEditProjectSubmit}
                                disabled={editingProject}
                                className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-60"
                            >
                                {editingProject ? "Guardando..." : "Guardar cambios"}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {showResetUiModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
                    <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900">
                        <h3 className="text-lg font-bold dark:text-white">Reset estado UI</h3>
                        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
                            Elige qué estado persistido quieres limpiar.
                        </p>
                        <div className="mt-5 space-y-2">
                            <button
                                onClick={() => handleResetUiAction("active_theory")}
                                className="w-full rounded-xl border border-zinc-200 px-4 py-2 text-left text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:text-white dark:hover:bg-zinc-800"
                            >
                                Solo teoría activa
                            </button>
                            <button
                                onClick={() => handleResetUiAction("dashboard_ui")}
                                className="w-full rounded-xl border border-zinc-200 px-4 py-2 text-left text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:text-white dark:hover:bg-zinc-800"
                            >
                                Solo UI dashboard
                            </button>
                            <button
                                onClick={() => handleResetUiAction("all")}
                                className="w-full rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-left text-sm font-bold text-amber-800 hover:bg-amber-100"
                            >
                                Todo (UI + teoría)
                            </button>
                        </div>
                        <div className="mt-5 flex justify-end">
                            <button
                                onClick={() => setShowResetUiModal(false)}
                                className="rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-500 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                            >
                                Cancelar
                            </button>
                        </div>
                    </div>
                </div>
            )}
            <AuthenticatedChatbot />
        </div>
    );
}






