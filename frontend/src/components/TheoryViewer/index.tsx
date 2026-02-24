import { useState } from "react";
import { apiClient } from "@/lib/api";
import InterviewModal from "@/components/InterviewModal";

interface Theory {
    id: string;
    version: number;
    generated_by: string;
    confidence_score: number;
    model_json: Record<string, any>;
    propositions: any[];
    gaps: any[];
    validation?: Record<string, any>;
}

interface TheoryViewerProps {
    projectId: string;
    theory: Theory;
    onExportComplete?: () => void;
}

export default function TheoryViewer({ projectId, theory, onExportComplete }: TheoryViewerProps) {
    const [isExporting, setIsExporting] = useState(false);
    const [exportingFormat, setExportingFormat] = useState<"pdf" | "pptx" | "xlsx" | "png">("pdf");
    const [expanded, setExpanded] = useState<Record<string, boolean>>({});
    const [openInterviewId, setOpenInterviewId] = useState<string | null>(null);
    const [highlightFragmentId, setHighlightFragmentId] = useState<string | null>(null);

    const toDisplayText = (value: any): string => {
        if (value == null) return "";
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        if (Array.isArray(value)) {
            return value.map((v) => toDisplayText(v)).filter(Boolean).join(" | ");
        }
        if (typeof value === "object") {
            // Prefer explicit textual fields when present
            if (typeof value.text === "string" && value.text.trim()) return String(value.text).trim();
            if (value.name && (value.type || value.horizon)) {
                const tags = [value.type, value.horizon].filter(Boolean).join("/");
                return tags ? `${String(value.name)} [${tags}]` : String(value.name);
            }
            if (value.name && value.evidence) return `${value.name}: ${toDisplayText(value.evidence)}`;
            if (value.gap_description) return toDisplayText(value.gap_description);
            if (value.theoretical_model_description) return toDisplayText(value.theoretical_model_description);
            if (value.selected_central_category) return toDisplayText(value.selected_central_category);
            if (value.central_phenomenon?.name) return toDisplayText(value.central_phenomenon.name);
            if (value.definition) return `${toDisplayText(value.name || "")}${value.name ? ": " : ""}${toDisplayText(value.definition)}`;
            if (value.evidence) return toDisplayText(value.evidence);
            if (value.description) return toDisplayText(value.description);
            if (value.id && value.name) return `${toDisplayText(value.name)} (${toDisplayText(value.id)})`;
            try {
                return JSON.stringify(value);
            } catch (_) {
                return String(value);
            }
        }
        return String(value);
    };

    const asItems = (value: any): any[] => {
        if (value == null) return [];
        if (Array.isArray(value)) return value;
        return [value];
    };

    const toggle = (key: string) => setExpanded((p) => ({ ...p, [key]: !p[key] }));

    const networkSummary = theory?.validation?.network_metrics_summary || {};
    const counts = networkSummary?.counts || {};
    const centrality = asItems(networkSummary?.category_centrality_top);
    const cooccurrence = asItems(networkSummary?.category_cooccurrence_top);
    const semanticEvidence = asItems(networkSummary?.semantic_evidence_top);
    const promptVersion =
        theory?.validation?.pipeline_runtime?.prompt_version ||
        theory?.validation?.pipeline_runtime?.promptVersion ||
        theory?.validation?.pipeline_runtime?.prompt ||
        "";

    const evidenceCoverage = (() => {
        const props = asItems(theory?.propositions);
        const cons = asItems(theory?.model_json?.consequences);
        const propsWithEvidence = props.filter((p) => Array.isArray(p?.evidence_ids) && p.evidence_ids.length > 0).length;
        const consWithEvidence = cons.filter((c) => Array.isArray(c?.evidence_ids) && c.evidence_ids.length > 0).length;
        return {
            propsTotal: props.length,
            propsWithEvidence,
            consTotal: cons.length,
            consWithEvidence,
        };
    })();

    const displayModelName = (name?: string) => {
        if (!name) return "";
        const n = String(name);
        if (n.includes("DeepSeek") || n.includes("Kimi") || n.includes("Kimi-K2.5") || n.includes("DeepSeek-V3.2-Speciale")) {
            return "GPT-5.2";
        }
        return n;
    };

    const centralCategory =
        toDisplayText(theory?.model_json?.selected_central_category) ||
        toDisplayText(theory?.model_json?.central_phenomenon?.name) ||
        "No disponible";

    const conditionsText =
        toDisplayText(theory?.model_json?.conditions) ||
        toDisplayText(theory?.model_json?.causal_conditions) ||
        "No disponible";

    const actionsText =
        toDisplayText(theory?.model_json?.actions) ||
        toDisplayText(theory?.model_json?.action_strategies) ||
        "No disponible";

    const consequencesText =
        toDisplayText(theory?.model_json?.consequences) ||
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
                            {asItems(theory?.model_json?.conditions || theory?.model_json?.causal_conditions).length > 0 ? (
                                <ul className={`space-y-2 ${expanded.conditions ? "" : "max-h-40 overflow-auto"}`}>
                                    {asItems(theory?.model_json?.conditions || theory?.model_json?.causal_conditions).map((it, i) => (
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
                            {asItems(theory?.model_json?.actions || theory?.model_json?.action_strategies).length > 0 ? (
                                <ul className={`space-y-2 ${expanded.actions ? "" : "max-h-40 overflow-auto"}`}>
                                    {asItems(theory?.model_json?.actions || theory?.model_json?.action_strategies).map((it, i) => (
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
                            {asItems(theory?.model_json?.consequences).length > 0 ? (
                                <ul className={`space-y-2 ${expanded.consequences ? "" : "max-h-40 overflow-auto"}`}>
                                    {asItems(theory?.model_json?.consequences).map((it, i) => (
                                        <li key={i} className="text-zinc-700 dark:text-zinc-300 break-words whitespace-pre-wrap">
                                            {toDisplayText(it)}
                                            {Array.isArray((it as any)?.evidence_ids) && (it as any).evidence_ids.length > 0 && (
                                                <div className="mt-1 text-[11px] text-zinc-500">
                                                    evidence_ids: {(it as any).evidence_ids.slice(0, 5).join(", ")}
                                                    {(it as any).evidence_ids.length > 5 ? " ..." : ""}
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
                                    {Array.isArray((prop as any)?.evidence_ids) && (prop as any).evidence_ids.length > 0 && (
                                        <div className="mt-1 text-[11px] text-zinc-500">
                                            evidence_ids: {(prop as any).evidence_ids.slice(0, 5).join(", ")}
                                            {(prop as any).evidence_ids.length > 5 ? " ..." : ""}
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
                                    Categorias: {counts.category_count ?? 0} · Codigos: {counts.code_count ?? 0} · Fragmentos: {counts.fragment_count ?? 0}
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
                                                {centrality.slice(0, 10).map((r: any, i: number) => (
                                                    <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
                                                        <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{r.category_name || r.category_id}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{r.pagerank ?? ""}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{r.gds_degree ?? ""}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{r.code_degree ?? ""}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{r.fragment_degree ?? ""}</td>
                                                    </tr>
                                                ))}
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
                                                {cooccurrence.slice(0, 10).map((r: any, i: number) => (
                                                    <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
                                                        <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{r.category_a_name || r.category_a_id}</td>
                                                        <td className="py-1 pr-2 text-zinc-700 dark:text-zinc-300">{r.category_b_name || r.category_b_id}</td>
                                                        <td className="py-1 pr-2 text-zinc-600 dark:text-zinc-400">{r.shared_fragments ?? ""}</td>
                                                    </tr>
                                                ))}
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
                                        {semanticEvidence.slice(0, expanded.evidence ? 50 : 15).map((bucket: any, i: number) => (
                                            <div key={i} className="border-t border-zinc-100 dark:border-zinc-800 pt-2">
                                                <div className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                                                    {bucket.category_name || bucket.category_id}
                                                </div>
                                                <div className="mt-1 space-y-2">
                                                    {asItems(bucket.fragments).slice(0, 3).map((f: any, j: number) => (
                                                        <div key={j} className="text-xs text-zinc-600 dark:text-zinc-400">
                                                            <div className="text-[11px] text-zinc-500">
                                                                fragment_id: {f.fragment_id || f.id} · score: {f.score ?? ""}
                                                            </div>
                                                            <div className="whitespace-pre-wrap break-words">{f.text}</div>
                                                            {(f.fragment_id || f.id) && (
                                                                <button
                                                                    onClick={() => openFragmentInTranscript(String(f.fragment_id || f.id))}
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
                                <button onClick={() => toggle("evidence")} className="mt-2 text-xs font-bold text-indigo-600">
                                    {expanded.evidence ? "Ver menos" : "Ver mas"}
                                </button>
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
