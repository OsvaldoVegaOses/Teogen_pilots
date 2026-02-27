"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import InterviewModal from "./InterviewModal";
import ExportPanel, { enqueueLocalExport } from "./ExportPanel";

export default function InterviewUpload({ projectId, onUploadSuccess }: { projectId: string, onUploadSuccess: () => void }) {
    const [file, setFile] = useState<File | null>(null);
    const [pseudonym, setPseudonym] = useState("");
    const [uploading, setUploading] = useState(false);
    const [message, setMessage] = useState("");
    const [interviews, setInterviews] = useState<Array<{
        id: string;
        created_at?: string;
        participant_pseudonym?: string;
        transcription_status?: string;
    }>>([]);
    const [openInterview, setOpenInterview] = useState<string | null>(null);

    const fetchInterviewStatuses = useCallback(async () => {
        if (!projectId) return;
        try {
            const response = await apiClient(`interviews/${projectId}`);
            if (response.ok) {
                const data = await response.json();
                const sorted = [...data].sort((a, b) => {
                    const aTime = new Date(a.created_at || 0).getTime();
                    const bTime = new Date(b.created_at || 0).getTime();
                    return bTime - aTime;
                });
                setInterviews(sorted);
            }
        } catch (error) {
            console.error("Error fetching interview statuses:", error);
        }
    }, [projectId]);

    useEffect(() => {
        fetchInterviewStatuses();
    }, [fetchInterviewStatuses]);

    useEffect(() => {
        if (!projectId) return;
        const intervalId = setInterval(fetchInterviewStatuses, 10000);
        return () => clearInterval(intervalId);
    }, [projectId, fetchInterviewStatuses]);

    const handleUpload = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!file) return;

        setUploading(true);
        setMessage("");

        const formData = new FormData();
        formData.append("file", file);
        if (pseudonym) formData.append("participant_pseudonym", pseudonym);

        try {
            // Note: apiClient automatically skips setting Content-Type for FormData
            const response = await apiClient(`interviews/upload?project_id=${projectId}`, {
                method: "POST",
                body: formData,
            });

            if (response.ok) {
                setMessage("✅ Entrevista subida y procesando...");
                setFile(null);
                setPseudonym("");
                fetchInterviewStatuses();
                if (onUploadSuccess) onUploadSuccess();
            } else {
                const err = await response.json();
                setMessage(`❌ Error: ${err.detail || "Error desconocido"}`);
            }
        } catch (error) {
            console.error("Upload failed", error);
            setMessage("❌ Error de conexión con el servidor.");
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="rounded-3xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-zinc-900/50">
            <h3 className="text-xl font-bold mb-4 dark:text-white">Subir Nueva Entrevista</h3>
            <form onSubmit={handleUpload} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-zinc-600 dark:text-zinc-300 mb-1">Seudónimo del Participante (opcional)</label>
                    <input
                        type="text"
                        value={pseudonym}
                        onChange={(e) => setPseudonym(e.target.value)}
                        placeholder="Ej: Participante A (puedes dejarlo vacío)"
                        className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-600 dark:border-zinc-800 dark:bg-zinc-950"
                    />
                </div>
                <div>
                    <label htmlFor={`interview-file-${projectId}`} className="block text-sm font-medium text-zinc-600 dark:text-zinc-300 mb-1">Archivo de Audio o Transcripción</label>
                    <input
                        id={`interview-file-${projectId}`}
                        name="file"
                        type="file"
                        accept="audio/*,text/plain,application/json"
                        title="Selecciona un archivo de audio o una transcripción"
                        aria-label="Archivo de audio o transcripción"
                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                        className="block w-full text-sm text-zinc-600 dark:text-zinc-300 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-bold file:bg-indigo-600 file:text-white hover:file:bg-indigo-700"
                    />
                </div>
                <button
                    type="submit"
                    disabled={uploading || !file}
                    className="w-full rounded-2xl bg-indigo-600 py-4 font-bold text-white transition-all hover:bg-indigo-700 disabled:opacity-50 active:scale-95"
                >
                    {uploading ? "Subiendo..." : "Iniciar Procesamiento"}
                </button>
                {message && <p className={`text-sm text-center font-medium ${message.includes('❌') ? 'text-red-500' : 'text-green-500'}`}>{message}</p>}

                {interviews.length > 0 && (
                    <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950">
                        <p className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-600 dark:text-zinc-300">Estado de procesamiento</p>
                        <div className="space-y-2">
                            {interviews.slice(0, 3).map((item) => {
                                const status = item.transcription_status || "unknown";
                                const statusLabel = status === "completed"
                                    ? "✅ Completado"
                                    : status === "processing"
                                        ? "⏳ Procesando"
                                        : status === "retrying"
                                            ? "🔄 Reintentando"
                                        : status === "failed"
                                            ? "❌ Falló"
                                            : "⚪ Pendiente";

                                return (
                                    <div key={item.id} className="flex items-center justify-between text-xs">
                                        <div className="flex items-center gap-3">
                                            <span className="truncate pr-2 text-zinc-700 dark:text-zinc-300">{item.participant_pseudonym || "Entrevista sin seudónimo"}</span>
                                            <button type="button" onClick={() => setOpenInterview(item.id)} className="text-indigo-600 text-xs font-bold">Ver</button>
                                            <button onClick={async () => {
                                                // start export single interview as json (fire-and-forget / poll)
                                                if (!projectId) return;
                                                try {
                                                    const resp = await apiClient(`interviews/export`, {
                                                        method: "POST",
                                                        body: JSON.stringify({
                                                            project_id: projectId,
                                                            interview_ids: [item.id],
                                                            scope: "selected",
                                                            format: "json",
                                                            include_metadata: true,
                                                            include_codes: true,
                                                            include_timestamps: true,
                                                            language: "es"
                                                        })
                                                    });
                                                    if (!resp.ok) {
                                                        console.error("Export failed", resp.status);
                                                    } else {
                                                        const data = await resp.json();
                                                        console.log("Export enqueued", data.task_id);
                                                        alert(`Export encolado (task ${data.task_id}). Revisa estado en exportaciones.`);
                                                    }
                                                } catch (e) {
                                                    console.error(e);
                                                    alert("Error iniciando export");
                                                }
                                            }} type="button" className="text-zinc-600 text-xs">Exportar</button>
                                        </div>
                                        <span className="font-medium">{statusLabel}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
                <div className="mt-3">
                    <button type="button" onClick={async () => {
                        if (!projectId) return;
                        try {
                            const resp = await apiClient(`interviews/export`, {
                                method: 'POST',
                                body: JSON.stringify({ project_id: projectId, scope: 'all_project', format: 'pdf', include_metadata: true, include_codes: true, include_timestamps: true, language: 'es' })
                            });
                            if (!resp.ok) {
                                alert('No se pudo encolar exportación');
                                return;
                            }
                            const data = await resp.json();
                            enqueueLocalExport(data.task_id);
                            alert(`Export encolado (task ${data.task_id})`);
                        } catch (e) { console.error(e); alert('Error iniciando export'); }
                    }} className="w-full rounded-2xl bg-indigo-600 py-2 font-bold text-white">Exportar todas las entrevistas (PDF)</button>
                </div>
                <div className="mt-3">
                    <ExportPanel projectId={projectId} />
                </div>
                {openInterview && (
                    <InterviewModal interviewId={openInterview} projectId={projectId} onClose={() => setOpenInterview(null)} />
                )}
            </form>
        </div>
    );
}
