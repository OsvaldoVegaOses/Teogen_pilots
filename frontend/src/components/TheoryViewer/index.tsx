import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import InterviewModal from "@/components/InterviewModal";

export interface Theory {
    id: string;
    version: number;
    generated_by: string;
    confidence_score: number;
    model_json: Record<string, unknown>;
    propositions: unknown[];
    gaps: unknown[];
    validation?: Record<string, unknown>;
}

interface TheoryViewerProps {
    projectId: string;
    theory: Theory;
    onExportComplete?: () => void;
    viewerState?: {
        sectionFilter?: string;
        claimTypeFilter?: string;
        page?: number;
        expanded?: Record<string, boolean>;
    };
    onViewerStateChange?: (state: {
        sectionFilter: string;
        claimTypeFilter: string;
        page: number;
        expanded: Record<string, boolean>;
    }) => void;
}

interface ClaimExplainEvidence {
    fragment_id: string;
    score?: number;
    rank?: number;
    text?: string;
    interview_id?: string;
}

interface ClaimExplainItem {
    claim_id: string;
    claim_type: string;
    section: string;
    order: number;
    text: string;
    categories: Array<{ id?: string; name?: string }>;
    evidence: ClaimExplainEvidence[];
    path_examples?: string[];
}

interface ClaimExplainResponse {
    source: string;
    total?: number;
    limit?: number;
    offset?: number;
    has_more?: boolean;
    section_filter?: string | null;
    claim_type_filter?: string | null;
    claim_count: number;
    claims: ClaimExplainItem[];
}

const CLAIMS_PAGE_SIZE = 10;
type LooseRecord = Record<string, unknown>;

function getEvidenceIds(value: unknown): string[] {
    if (!value || typeof value !== "object") return [];
    const evidenceIds = (value as LooseRecord).evidence_ids;
    if (!Array.isArray(evidenceIds)) return [];
    return evidenceIds.map((id) => String(id));
}

function isSameExpandedState(a: Record<string, boolean>, b: Record<string, boolean>): boolean {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    if (aKeys.length !== bKeys.length) return false;
    for (const key of aKeys) {
        if (a[key] !== b[key]) return false;
    }
    return true;
}

export default function TheoryViewer({
    projectId,
    theory,
    onExportComplete,
    viewerState,
    onViewerStateChange,
}: TheoryViewerProps) {
    const [isExporting, setIsExporting] = useState(false);
    const [exportingFormat, setExportingFormat] = useState<"pdf" | "pptx" | "xlsx" | "png">("pdf");
    const [expanded, setExpanded] = useState<Record<string, boolean>>(viewerState?.expanded || {});
    const [openInterviewId, setOpenInterviewId] = useState<string | null>(null);
    const [highlightFragmentId, setHighlightFragmentId] = useState<string | null>(null);
    const [claimsData, setClaimsData] = useState<ClaimExplainResponse | null>(null);
    const [claimsLoading, setClaimsLoading] = useState(false);
    const [claimsError, setClaimsError] = useState<string | null>(null);
    const [claimsSectionFilter, setClaimsSectionFilter] = useState<string>(viewerState?.sectionFilter || "all");
    const [claimsTypeFilter, setClaimsTypeFilter] = useState<string>(viewerState?.claimTypeFilter || "all");
    const [claimsPage, setClaimsPage] = useState(viewerState?.page || 0);
    const modelJson = (theory?.model_json || {}) as LooseRecord;

    const toDisplayText = (value: unknown): string => {
        if (value == null) return "";
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        if (Array.isArray(value)) {
            return value.map((v) => toDisplayText(v)).filter(Boolean).join(" | ");
        }
        if (typeof value === "object") {
            const v = value as LooseRecord;
            // Prefer explicit textual fields when present
            if (typeof v.text === "string" && v.text.trim()) return String(v.text).trim();
            if (v.name && (v.type || v.horizon)) {
                const tags = [v.type, v.horizon].filter(Boolean).join("/");
                return tags ? `${String(v.name)} [${tags}]` : String(v.name);
            }
            if (v.name && v.evidence) return `${v.name}: ${toDisplayText(v.evidence)}`;
            if (v.gap_description) return toDisplayText(v.gap_description);
            if (v.theoretical_model_description) return toDisplayText(v.theoretical_model_description);
            if (v.selected_central_category) return toDisplayText(v.selected_central_category);
            if (v.central_phenomenon && typeof v.central_phenomenon === "object") {
                const centralPhenomenon = v.central_phenomenon as LooseRecord;
                if (centralPhenomenon.name) return toDisplayText(centralPhenomenon.name);
            }
            if (v.definition) return `${toDisplayText(v.name || "")}${v.name ? ": " : ""}${toDisplayText(v.definition)}`;
            if (v.evidence) return toDisplayText(v.evidence);
            if (v.description) return toDisplayText(v.description);
            if (v.id && v.name) return `${toDisplayText(v.name)} (${toDisplayText(v.id)})`;
            try {
                return JSON.stringify(value);
            } catch {
                return String(value);
            }
        }
        return String(value);
    };

    const asItems = (value: unknown): unknown[] => {
        if (value == null) return [];
        if (Array.isArray(value)) return value;
        return [value];
    };

    const toggle = (key: string) => setExpanded((p) => ({ ...p, [key]: !p[key] }));

    useEffect(() => {
        const nextSection = viewerState?.sectionFilter || "all";
        const nextType = viewerState?.claimTypeFilter || "all";
        const nextPage = viewerState?.page || 0;
        const nextExpanded = viewerState?.expanded || {};
        setClaimsSectionFilter((prev) => (prev === nextSection ? prev : nextSection));
        setClaimsTypeFilter((prev) => (prev === nextType ? prev : nextType));
        setClaimsPage((prev) => (prev === nextPage ? prev : nextPage));
        setExpanded((prev) => (isSameExpandedState(prev, nextExpanded) ? prev : nextExpanded));
    }, [theory?.id, viewerState?.sectionFilter, viewerState?.claimTypeFilter, viewerState?.page, viewerState?.expanded]);

    useEffect(() => {
        if (!onViewerStateChange) return;
        onViewerStateChange({
            sectionFilter: claimsSectionFilter,
            claimTypeFilter: claimsTypeFilter,
            page: claimsPage,
            expanded,
        });
    }, [claimsSectionFilter, claimsTypeFilter, claimsPage, expanded, onViewerStateChange]);

    useEffect(() => {
        let ignore = false;
        const loadClaimsExplain = async () => {
            if (!projectId || !theory?.id) return;
            setClaimsLoading(true);
            setClaimsError(null);
            try {
                const params = new URLSearchParams();
                params.set("limit", String(CLAIMS_PAGE_SIZE));
                params.set("offset", String(claimsPage * CLAIMS_PAGE_SIZE));
                if (claimsSectionFilter !== "all") params.set("section", claimsSectionFilter);
                if (claimsTypeFilter !== "all") params.set("claim_type", claimsTypeFilter);

                const response = await apiClient(
                    `/projects/${projectId}/theories/${theory.id}/claims/explain?${params.toString()}`,
                    { method: "GET" }
                );
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = (await response.json()) as ClaimExplainResponse;
                if (!ignore) {
                    setClaimsData(data);
                }
            } catch {
                if (!ignore) {
                    setClaimsError("No se pudo cargar la evidencia por claim.");
                    setClaimsData(null);
                }
            } finally {
                if (!ignore) setClaimsLoading(false);
            }
        };
        loadClaimsExplain();
        return () => {
            ignore = true;
        };
    }, [projectId, theory?.id, claimsPage, claimsSectionFilter, claimsTypeFilter]);

    const validation = (theory?.validation || {}) as LooseRecord;
    const networkSummary = (validation.network_metrics_summary || {}) as LooseRecord;
    const counts = (networkSummary.counts || {}) as LooseRecord;
    const centrality = asItems(networkSummary.category_centrality_top);
    const cooccurrence = asItems(networkSummary.category_cooccurrence_top);
    const semanticEvidence = asItems(networkSummary.semantic_evidence_top);
    const pipelineRuntime = (validation.pipeline_runtime || {}) as LooseRecord;
    const promptVersion =
        pipelineRuntime.prompt_version ||
        pipelineRuntime.promptVersion ||
        pipelineRuntime.prompt ||
        "";

    const evidenceCoverage = (() => {
        const props = asItems(theory?.propositions);
        const cons = asItems(modelJson.consequences);
        const propsWithEvidence = props.filter((p) => getEvidenceIds(p).length > 0).length;
        const consWithEvidence = cons.filter((c) => getEvidenceIds(c).length > 0).length;
        return {
            propsTotal: props.length,
            propsWithEvidence,
            consTotal: cons.length,
            consWithEvidence,
        };
    })();

    const claimsTotal = claimsData?.total ?? claimsData?.claim_count ?? 0;
    const claimsOffset = claimsData?.offset ?? claimsPage * CLAIMS_PAGE_SIZE;
    const claimsCount = claimsData?.claim_count ?? 0;
    const claimsFrom = claimsTotal > 0 ? claimsOffset + 1 : 0;
    const claimsTo = claimsTotal > 0 ? claimsOffset + claimsCount : 0;
    const claimsHasMore =
        typeof claimsData?.has_more === "boolean"
            ? claimsData.has_more
            : claimsOffset + claimsCount < claimsTotal;

    const displayModelName = (name?: string) => {
        if (!name) return "";
        const n = String(name);
        if (n.includes("DeepSeek") || n.includes("Kimi") || n.includes("Kimi-K2.5") || n.includes("DeepSeek-V3.2-Speciale")) {
            return "GPT-5.2";
        }
        return n;
    };

    const centralCategory =
        toDisplayText(modelJson.selected_central_category) ||
        toDisplayText((modelJson.central_phenomenon as LooseRecord | undefined)?.name) ||
        "No disponible";

    const conditionsText =
        toDisplayText(modelJson.conditions) ||
        toDisplayText(modelJson.causal_conditions) ||
        "No disponible";

    const actionsText =
        toDisplayText(modelJson.actions) ||
        toDisplayText(modelJson.action_strategies) ||
        "No disponible";

    const consequencesText =
        toDisplayText(modelJson.consequences) ||
        "No disponible";

    const handleExport = async (format: "pdf" | "pptx" | "xlsx" | "png") => {
        setIsExporting(true);
        setExportingFormat(format);
        try {
            const response = await apiClient(`/projects/${projectId}/theories/${theory.id}/export?format=${format}`, {
                method: "POST",
            });

            if (response.ok) {
                const data = await response.json();
                const link = document.createElement("a");
                link.href = data.download_url;
                link.download = data.filename || `Theory_Report.${format}`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                if (onExportComplete) onExportComplete();
            } else {
                alert("Error al generar el reporte. Intente nuevamente.");
            }
        } catch (error) {
            console.error("Export error:", error);
            alert("Error de conexion al exportar.");
        } finally {
            setIsExporting(false);
        }
    };

    const openFragmentInTranscript = async (fragmentId: string) => {
        try {
            const resp = await apiClient(`search/fragments/lookup`, {
                method: "POST",
                body: JSON.stringify({
                    project_id: projectId,
                    fragment_ids: [fragmentId],
                }),
            });
            if (!resp.ok) return;
            const data = await resp.json();
            const hit = Array.isArray(data) ? data[0] : null;
            if (!hit?.interview_id) return;
            setHighlightFragmentId(fragmentId);
            setOpenInterviewId(String(hit.interview_id));
        } catch (e) {
            console.warn(e);
        }
    };

    return (
        <div className="bg-white dark:bg-zinc-900 rounded-3xl border border-zinc-200 dark:border-zinc-800 p-8 shadow-sm">
            <div className="flex justify-between items-start mb-8 gap-4">
                <div>
                    <h2 className="text-2xl font-bold dark:text-white mb-2">
                        Teoria Fundamentada (v{theory.version})
                    </h2>
                    <div className="flex items-center gap-3 text-sm text-zinc-500">
                        <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-medium dark:bg-indigo-900/30 dark:text-indigo-300">
                            {displayModelName(theory.generated_by)}
                        </span>
                        <span>Confidence: {(theory.confidence_score * 100).toFixed(1)}%</span>
                        {promptVersion && (
                            <span className="bg-zinc-100 text-zinc-700 px-3 py-1 rounded-full font-bold text-xs">
                                Prompt: {String(promptVersion)}
                            </span>
                        )}
                    </div>
                </div>

                <div className="flex flex-wrap gap-2">
                    {(["pdf", "pptx", "xlsx", "png"] as const).map((fmt) => (
                        <button
                            key={fmt}
                            onClick={() => handleExport(fmt)}
                            disabled={isExporting}
                            className="bg-zinc-900 text-white px-4 py-2 rounded-xl font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all uppercase text-xs"
                        >
                            {isExporting && exportingFormat === fmt ? `Generando ${fmt}...` : `Exportar ${fmt}`}
                        </button>
                    ))}
                </div>
            </div>

                <div className="grid gap-8 lg:grid-cols-2">
                <div className="space-y-6">
                    <h3 className="text-lg font-bold text-zinc-800 dark:text-zinc-200 border-b pb-2">Modelo Paradigmatico</h3>

                    <div className="bg-indigo-50 dark:bg-indigo-900/10 p-6 rounded-2xl border border-indigo-100 dark:border-indigo-800/30">
                        <div className="text-sm font-bold text-indigo-600 uppercase tracking-widest mb-1">Categoria Central</div>
                        <div className="text-xl font-bold text-indigo-900 dark:text-indigo-200 break-words whitespace-pre-wrap">
                            {centralCategory}
                        </div>
                    </div>

                    <div className="grid gap-4 text-sm">
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Condiciones</span>
                            {asItems(modelJson.conditions || modelJson.causal_conditions).length > 0 ? (
                                <ul className={`space-y-2 ${expanded.conditions ? "" : "max-h-40 overflow-auto"}`}>
                                    {asItems(modelJson.conditions || modelJson.causal_conditions).map((it, i) => (
                                        <li key={i} className="text-zinc-700 dark:text-zinc-300 break-words whitespace-pre-wrap">
                                            {toDisplayText(it)}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="break-words whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">{conditionsText}</p>
                            )}
                            <button onClick={() => toggle("conditions")} className="mt-2 text-xs font-bold text-indigo-600">
                                {expanded.conditions ? "Ver menos" : "Ver mas"}
                            </button>
                        </div>
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Acciones / Interacciones</span>
                            {asItems(modelJson.actions || modelJson.action_strategies).length > 0 ? (
                                <ul className={`space-y-2 ${expanded.actions ? "" : "max-h-40 overflow-auto"}`}>
                                    {asItems(modelJson.actions || modelJson.action_strategies).map((it, i) => (
                                        <li key={i} className="text-zinc-700 dark:text-zinc-300 break-words whitespace-pre-wrap">
                                            {toDisplayText(it)}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="break-words whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">{actionsText}</p>
                            )}
                            <button onClick={() => toggle("actions")} className="mt-2 text-xs font-bold text-indigo-600">
                                {expanded.actions ? "Ver menos" : "Ver mas"}
                            </button>
                        </div>
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Consecuencias</span>
                            {asItems(modelJson.consequences).length > 0 ? (
                                <ul className={`space-y-2 ${expanded.consequences ? "" : "max-h-40 overflow-auto"}`}>
                                    {asItems(modelJson.consequences).map((it, i) => (
                                        <li key={i} className="text-zinc-700 dark:text-zinc-300 break-words whitespace-pre-wrap">
                                            {toDisplayText(it)}
                                            {getEvidenceIds(it).length > 0 && (
                                                <div className="mt-1 text-[11px] text-zinc-500">
                                                    evidence_ids: {getEvidenceIds(it).slice(0, 5).join(", ")}
                                                    {getEvidenceIds(it).length > 5 ? " ..." : ""}
                                                </div>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="break-words whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">{consequencesText}</p>
                            )}
                            <button onClick={() => toggle("consequences")} className="mt-2 text-xs font-bold text-indigo-600">
                                {expanded.consequences ? "Ver menos" : "Ver mas"}
                            </button>
                        </div>
                    </div>
                </div>

                <div>
                    <h3 className="text-lg font-bold text-zinc-800 dark:text-zinc-200 border-b pb-2 mb-6">Proposiciones Teoricas</h3>
                    <ul className="space-y-4">
                        {theory.propositions.map((prop, idx) => (
                            <li key={idx} className="flex gap-4 p-4 rounded-xl hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors">
                                <span className="flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold mt-0.5">
                                    {idx + 1}
                                </span>
                                <div className="min-w-0">
                                    <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed text-sm break-words whitespace-pre-wrap">
                                        {toDisplayText(prop)}
                                    </p>
                                    {getEvidenceIds(prop).length > 0 && (
                                        <div className="mt-1 text-[11px] text-zinc-500">
                                            evidence_ids: {getEvidenceIds(prop).slice(0, 5).join(", ")}
                                            {getEvidenceIds(prop).length > 5 ? " ..." : ""}
                                        </div>
                                    )}
                                </div>
                            </li>
                        ))}
                    </ul>

                    <div className="mt-8 pt-6 border-t border-zinc-100 dark:border-zinc-800">
                        <h4 className="font-bold text-zinc-700 dark:text-zinc-200 mb-3">Cuadros y correlaciones (Neo4j/Qdrant)</h4>
                        <div className="grid gap-3 text-sm">
                            <div className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-4 bg-white dark:bg-zinc-900/30">
                                <div className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Cobertura de evidencia</div>
                                <div className="text-zinc-600 dark:text-zinc-400">
                                    Proposiciones con evidencia: {evidenceCoverage.propsWithEvidence}/{evidenceCoverage.propsTotal} · Consecuencias con evidencia: {evidenceCoverage.consWithEvidence}/{evidenceCoverage.consTotal}
                                </div>
                            </div>

                            <div className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-4 bg-white dark:bg-zinc-900/30">
                                <div className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Grafo (Neo4j)</div>
                                <div className="text-zinc-600 dark:text-zinc-400">
                                    Categorias: {Number(counts.category_count ?? 0)} · Codigos: {Number(counts.code_count ?? 0)} · Fragmentos: {Number(counts.fragment_count ?? 0)}
                                </div>
                                {centrality.length > 0 && (
                                    <div className="mt-3 overflow-auto">
                                        <table className="w-full text-xs">
                                            <thead>
                                                <tr className="text-left text-zinc-500">
                                                    <th className="py-1 pr-2">Categoria</th>
                                                    <th className="py-1 pr-2">PageRank</th>
                                                    <th className="py-1 pr-2">GDS degree</th>
                                                    <th className="py-1 pr-2">Code deg</th>
                                                    <th className="py-1 pr-2">Frag deg</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {centrality.slice(0, 10).map((row, i: number) => {
                                                    const r = row as LooseRecord;
                                                    return (
                                                    <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
                                                        <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{toDisplayText(r.category_name || r.category_id)}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{toDisplayText(r.pagerank ?? "")}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{toDisplayText(r.gds_degree ?? "")}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{toDisplayText(r.code_degree ?? "")}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{toDisplayText(r.fragment_degree ?? "")}</td>
                                                    </tr>
                                                )})}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                                {cooccurrence.length > 0 && (
                                    <div className="mt-3 overflow-auto">
                                        <div className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Coocurrencias (proxy de correlacion)</div>
                                        <table className="w-full text-xs">
                                            <thead>
                                                <tr className="text-left text-zinc-500">
                                                    <th className="py-1 pr-2">A</th>
                                                    <th className="py-1 pr-2">B</th>
                                                    <th className="py-1 pr-2">Shared</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {cooccurrence.slice(0, 10).map((row, i: number) => {
                                                    const r = row as LooseRecord;
                                                    return (
                                                    <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
                                                        <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{toDisplayText(r.category_a_name || r.category_a_id)}</td>
                                                        <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{toDisplayText(r.category_b_name || r.category_b_id)}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{toDisplayText(r.shared_fragments ?? "")}</td>
                                                    </tr>
                                                )})}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>

                            <div className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-4 bg-white dark:bg-zinc-900/30">
                                <div className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2">Evidencia semantica (Qdrant)</div>
                                {semanticEvidence.length === 0 ? (
                                    <div className="text-zinc-500">Sin evidencia registrada en validacion.</div>
                                ) : (
                                    <div className={`space-y-3 ${expanded.evidence ? "" : "max-h-72 overflow-auto"}`}>
                                        {semanticEvidence.slice(0, expanded.evidence ? 50 : 15).map((item, i: number) => {
                                            const bucket = item as LooseRecord;
                                            return (
                                            <div key={i} className="border-t border-zinc-100 dark:border-zinc-800 pt-2">
                                                <div className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                                                    {toDisplayText(bucket.category_name || bucket.category_id)}
                                                </div>
                                                <div className="mt-1 space-y-2">
                                                    {asItems(bucket.fragments).slice(0, 3).map((fragment, j: number) => {
                                                        const f = fragment as LooseRecord;
                                                        return (
                                                        <div key={j} className="text-xs text-zinc-600 dark:text-zinc-400">
                                                            <div className="text-[11px] text-zinc-500">
                                                                fragment_id: {toDisplayText(f.fragment_id || f.id)} · score: {toDisplayText(f.score ?? "")}
                                                            </div>
                                                            <div className="whitespace-pre-wrap break-words">{toDisplayText(f.text)}</div>
                                                            {Boolean(f.fragment_id || f.id) && (
                                                                <button
                                                                    onClick={() => openFragmentInTranscript(String(f.fragment_id || f.id))}
                                                                    className="mt-1 text-[11px] font-bold text-indigo-600"
                                                                >
                                                                    Abrir en transcripcion
                                                                </button>
                                                            )}
                                                        </div>
                                                    )})}
                                                </div>
                                            </div>
                                        )})}
                                    </div>
                                )}
                                <button onClick={() => toggle("evidence")} className="mt-2 text-xs font-bold text-indigo-600">
                                    {expanded.evidence ? "Ver menos" : "Ver mas"}
                                </button>
                            </div>

                            <div className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-4 bg-white dark:bg-zinc-900/30">
                                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                                    <div>
                                        <div className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Ver evidencia por claim</div>
                                        <div className="text-[11px] text-zinc-500">
                                            Fuente: {claimsData?.source || "cargando"} · Total: {claimsTotal}
                                        </div>
                                    </div>
                                    <div className="flex gap-2">
                                        <select
                                            value={claimsSectionFilter}
                                            onChange={(e) => {
                                                setClaimsSectionFilter(e.target.value);
                                                setClaimsPage(0);
                                            }}
                                            className="text-xs rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-1"
                                        >
                                            <option value="all">Seccion: Todas</option>
                                            <option value="conditions">Condiciones</option>
                                            <option value="context">Contexto</option>
                                            <option value="intervening_conditions">Intervinientes</option>
                                            <option value="actions">Acciones</option>
                                            <option value="consequences">Consecuencias</option>
                                            <option value="propositions">Proposiciones</option>
                                        </select>
                                        <select
                                            value={claimsTypeFilter}
                                            onChange={(e) => {
                                                setClaimsTypeFilter(e.target.value);
                                                setClaimsPage(0);
                                            }}
                                            className="text-xs rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-1"
                                        >
                                            <option value="all">Tipo: Todos</option>
                                            <option value="condition">Condition</option>
                                            <option value="action">Action</option>
                                            <option value="consequence">Consequence</option>
                                            <option value="proposition">Proposition</option>
                                            <option value="gap">Gap</option>
                                        </select>
                                    </div>
                                </div>

                                {claimsLoading ? (
                                    <div className="text-sm text-zinc-500">Cargando evidencia por claim...</div>
                                ) : claimsError ? (
                                    <div className="text-sm text-amber-600">{claimsError}</div>
                                ) : (
                                    <>
                                        {(claimsData?.claims || []).length === 0 ? (
                                            <div className="text-sm text-zinc-500">Sin claims para los filtros seleccionados.</div>
                                        ) : (
                                            <div className={`space-y-3 ${expanded.claimsExplain ? "" : "max-h-80 overflow-auto"}`}>
                                                {(claimsData?.claims || []).map((claim: ClaimExplainItem, idx: number) => (
                                                    <div key={`${claim.claim_id || idx}`} className="border-t border-zinc-100 dark:border-zinc-800 pt-2">
                                                        <div className="text-xs font-bold text-zinc-700 dark:text-zinc-300 break-words">
                                                            [{claim.section}] {claim.text}
                                                        </div>
                                                        {asItems(claim.categories).length > 0 && (
                                                            <div className="mt-1 text-[11px] text-zinc-500 break-words">
                                                                Categorias: {asItems(claim.categories).map((category) => {
                                                                    const cat = category as LooseRecord;
                                                                    return cat?.name || cat?.id;
                                                                }).filter(Boolean).join(", ")}
                                                            </div>
                                                        )}
                                                        <div className="mt-1 space-y-1">
                                                            {claim.evidence.slice(0, 5).map((ev: ClaimExplainEvidence, j: number) => (
                                                                <div key={`${ev.fragment_id}-${j}`} className="text-[11px] text-zinc-600 dark:text-zinc-400">
                                                                    <div>
                                                                        fragment_id: {ev.fragment_id} · score: {ev.score ?? ""} · rank: {ev.rank ?? ""}
                                                                    </div>
                                                                    {ev.text && <div className="break-words whitespace-pre-wrap">{ev.text}</div>}
                                                                    {ev.fragment_id && (
                                                                        <button
                                                                            onClick={() => openFragmentInTranscript(String(ev.fragment_id))}
                                                                            className="mt-1 text-[11px] font-bold text-indigo-600"
                                                                        >
                                                                            Abrir en transcripcion
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        <div className="mt-3 flex items-center justify-between">
                                            <button
                                                onClick={() => setClaimsPage((p) => Math.max(0, p - 1))}
                                                disabled={claimsPage <= 0 || claimsLoading}
                                                className="text-xs px-2 py-1 rounded border border-zinc-300 dark:border-zinc-700 disabled:opacity-50"
                                            >
                                                Anterior
                                            </button>
                                            <div className="text-[11px] text-zinc-500">
                                                Mostrando {claimsFrom}-{claimsTo} de {claimsTotal}
                                            </div>
                                            <button
                                                onClick={() => setClaimsPage((p) => p + 1)}
                                                disabled={!claimsHasMore || claimsLoading}
                                                className="text-xs px-2 py-1 rounded border border-zinc-300 dark:border-zinc-700 disabled:opacity-50"
                                            >
                                                Siguiente
                                            </button>
                                        </div>
                                        <button onClick={() => toggle("claimsExplain")} className="mt-2 text-xs font-bold text-indigo-600">
                                            {expanded.claimsExplain ? "Ver menos" : "Ver mas"}
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>

                    {theory.gaps.length > 0 && (
                        <div className="mt-8 pt-6 border-t border-zinc-100 dark:border-zinc-800">
                            <h4 className="font-bold text-amber-600 mb-3">Brechas Identificadas</h4>
                            <ul className="list-disc list-inside text-sm text-zinc-500 space-y-1 pl-2">
                                {theory.gaps.map((gap, i) => (
                                    <li key={i} className="break-words whitespace-pre-wrap">{toDisplayText(gap)}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>

            {openInterviewId && (
                <InterviewModal
                    interviewId={openInterviewId}
                    projectId={projectId}
                    onClose={() => {
                        setOpenInterviewId(null);
                        setHighlightFragmentId(null);
                    }}
                    highlightFragment={highlightFragmentId}
                />
            )}
        </div>
    );
}
