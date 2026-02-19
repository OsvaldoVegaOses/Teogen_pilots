import { useState } from "react";
import { apiClient } from "@/lib/api";

interface Theory {
    id: string;
    version: number;
    generated_by: string;
    confidence_score: number;
    model_json: {
        selected_central_category: string;
        conditions: string;
        actions: string;
        consequences: string;
    };
    propositions: string[];
    gaps: string[];
}

interface TheoryViewerProps {
    projectId: string;
    theory: Theory;
    onExportComplete?: () => void;
}

export default function TheoryViewer({ projectId, theory, onExportComplete }: TheoryViewerProps) {
    const [isExporting, setIsExporting] = useState(false);

    const handleExport = async () => {
        setIsExporting(true);
        try {
            const response = await apiClient(`/projects/${projectId}/theories/${theory.id}/export`, {
                method: "POST",
            });

            if (response.ok) {
                const data = await response.json();
                // Create a temporary link to trigger the download
                const link = document.createElement("a");
                link.href = data.download_url;
                link.download = data.filename || "Theory_Report.pdf";
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                if (onExportComplete) onExportComplete();
            } else {
                console.error("Export failed");
                alert("Error al generar el reporte. Intente nuevamente.");
            }
        } catch (error) {
            console.error("Export error:", error);
            alert("Error de conexión al exportar.");
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <div className="bg-white dark:bg-zinc-900 rounded-3xl border border-zinc-200 dark:border-zinc-800 p-8 shadow-sm">
            <div className="flex justify-between items-start mb-8">
                <div>
                    <h2 className="text-2xl font-bold dark:text-white mb-2">
                        Teoría Fundamentada (v{theory.version})
                    </h2>
                    <div className="flex items-center gap-3 text-sm text-zinc-500">
                        <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded font-medium dark:bg-indigo-900/30 dark:text-indigo-300">
                            {theory.generated_by}
                        </span>
                        <span>Confidence: {(theory.confidence_score * 100).toFixed(1)}%</span>
                    </div>
                </div>

                <button
                    onClick={handleExport}
                    disabled={isExporting}
                    className="flex items-center gap-2 bg-zinc-900 text-white px-5 py-2.5 rounded-xl font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-zinc-500/10"
                >
                    {isExporting ? (
                        <>
                            <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Generando PDF...
                        </>
                    ) : (
                        <>
                            📥 Exportar Informe PDF
                        </>
                    )}
                </button>
            </div>

            <div className="grid gap-8 lg:grid-cols-2">
                {/* Visual Model Section */}
                <div className="space-y-6">
                    <h3 className="text-lg font-bold text-zinc-800 dark:text-zinc-200 border-b pb-2">Modelo Paradigmático</h3>

                    <div className="bg-indigo-50 dark:bg-indigo-900/10 p-6 rounded-2xl border border-indigo-100 dark:border-indigo-800/30">
                        <div className="text-sm font-bold text-indigo-600 uppercase tracking-widest mb-1">Categoría Central</div>
                        <div className="text-xl font-bold text-indigo-900 dark:text-indigo-200">
                            {theory.model_json.selected_central_category}
                        </div>
                    </div>

                    <div className="grid gap-4 text-sm">
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Condiciones</span>
                            {theory.model_json.conditions}
                        </div>
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Acciones / Interacciones</span>
                            {theory.model_json.actions}
                        </div>
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-700 dark:text-zinc-300 block mb-1">Consecuencias</span>
                            {theory.model_json.consequences}
                        </div>
                    </div>
                </div>

                {/* Propositions Section */}
                <div>
                    <h3 className="text-lg font-bold text-zinc-800 dark:text-zinc-200 border-b pb-2 mb-6">Proposiciones Teóricas</h3>
                    <ul className="space-y-4">
                        {theory.propositions.map((prop, idx) => (
                            <li key={idx} className="flex gap-4 p-4 rounded-xl hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors">
                                <span className="flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold mt-0.5">
                                    {idx + 1}
                                </span>
                                <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed text-sm">
                                    {prop}
                                </p>
                            </li>
                        ))}
                    </ul>

                    {theory.gaps.length > 0 && (
                        <div className="mt-8 pt-6 border-t border-zinc-100 dark:border-zinc-800">
                            <h4 className="font-bold text-amber-600 mb-3 flex items-center gap-2">
                                ⚠️ Brechas Identificadas
                            </h4>
                            <ul className="list-disc list-inside text-sm text-zinc-500 space-y-1 pl-2">
                                {theory.gaps.map((gap, i) => (
                                    <li key={i}>{gap}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
