import { useState } from "react";
import { apiClient } from "@/lib/api";

interface Theory {
    id: string;
    version: number;
    generated_by: string;
    confidence_score: number;
    model_json: Record<string, any>;
    propositions: any[];
    gaps: any[];
}

interface TheoryViewerProps {
    projectId: string;
    theory: Theory;
    onExportComplete?: () => void;
}

export default function TheoryViewer({ projectId, theory, onExportComplete }: TheoryViewerProps) {
    const [isExporting, setIsExporting] = useState(false);
    const [exportingFormat, setExportingFormat] = useState<"pdf" | "pptx" | "xlsx" | "png">("pdf");

    const toDisplayText = (value: any): string => {
        if (value == null) return "";
        if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
            return String(value);
        }
        if (Array.isArray(value)) {
            return value.map((v) => toDisplayText(v)).filter(Boolean).join(" | ");
        }
        if (typeof value === "object") {
            if (value.name && value.evidence) return `${value.name}: ${toDisplayText(value.evidence)}`;
            if (value.gap_description) return toDisplayText(value.gap_description);
            if (value.theoretical_model_description) return toDisplayText(value.theoretical_model_description);
            if (value.selected_central_category) return toDisplayText(value.selected_central_category);
            if (value.central_phenomenon?.name) return toDisplayText(value.central_phenomenon.name);
            if (value.definition) return `${toDisplayText(value.name || "")}${value.name ? ": " : ""}${toDisplayText(value.definition)}`;
            if (value.evidence) return toDisplayText(value.evidence);
            if (value.description) return toDisplayText(value.description);
            if (value.id && value.name) return `${toDisplayText(value.name)} (${toDisplayText(value.id)})`;
            return JSON.stringify(value);
        }
        return String(value);
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

    return (
        <div className="bg-white dark:bg-zinc-900 rounded-3xl border border-zinc-200 dark:border-zinc-800 p-8 shadow-sm">
            <div className="flex justify-between items-start mb-8 gap-4">
                <div>
                    <h2 className="text-2xl font-bold dark:text-white mb-2">
                        Teoria Fundamentada (v{theory.version})
                    </h2>
                    <div className="flex items-center gap-3 text-sm text-zinc-500">
                        <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-medium dark:bg-indigo-900/30 dark:text-indigo-300">
                            {theory.generated_by}
                        </span>
                        <span>Confidence: {(theory.confidence_score * 100).toFixed(1)}%</span>
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
                        <div className="text-xl font-bold text-indigo-900 dark:text-indigo-200">
                            {centralCategory}
                        </div>
                    </div>

                    <div className="grid gap-4 text-sm">
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Condiciones</span>
                            {conditionsText}
                        </div>
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Acciones / Interacciones</span>
                            {actionsText}
                        </div>
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Consecuencias</span>
                            {consequencesText}
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
                                <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed text-sm">
                                    {toDisplayText(prop)}
                                </p>
                            </li>
                        ))}
                    </ul>

                    {theory.gaps.length > 0 && (
                        <div className="mt-8 pt-6 border-t border-zinc-100 dark:border-zinc-800">
                            <h4 className="font-bold text-amber-600 mb-3">Brechas Identificadas</h4>
                            <ul className="list-disc list-inside text-sm text-zinc-500 space-y-1 pl-2">
                                {theory.gaps.map((gap, i) => (
                                    <li key={i}>{toDisplayText(gap)}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
