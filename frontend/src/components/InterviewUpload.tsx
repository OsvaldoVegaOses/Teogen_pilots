"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api";
import InterviewModal from "./InterviewModal";

type InterviewStatusItem = {
    id: string;
    created_at?: string;
    participant_pseudonym?: string;
    transcription_status?: string;
    transcription_method?: string;
};

const IN_PROGRESS_STATUSES = new Set(["processing", "retrying", "pending"]);

function getStatusLabel(statusRaw?: string): string {
    const status = (statusRaw || "").toLowerCase();
    if (status === "completed") return "Completado";
    if (status === "processing") return "Procesando";
    if (status === "retrying") return "Reintentando";
    if (status === "failed") return "Falló";
    return "Pendiente";
}

function getStatusTone(statusRaw?: string): string {
    const status = (statusRaw || "").toLowerCase();
    if (status === "completed") return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300";
    if (status === "failed") return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300";
    if (status === "processing" || status === "retrying") {
        return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
    }
    return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
}

function formatDate(value?: string): string {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("es-CL", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export default function InterviewUpload({ projectId, onUploadSuccess }: { projectId: string; onUploadSuccess: () => void }) {
    const [file, setFile] = useState<File | null>(null);
    const [pseudonym, setPseudonym] = useState("");
    const [uploading, setUploading] = useState(false);
    const [message, setMessage] = useState("");
    const [interviews, setInterviews] = useState<InterviewStatusItem[]>([]);
    const [openInterview, setOpenInterview] = useState<string | null>(null);

    const uploadTrackingStorageKey = `upload_tracking_${projectId}`;
    const processingCount = useMemo(
        () => interviews.filter((item) => IN_PROGRESS_STATUSES.has((item.transcription_status || "").toLowerCase())).length,
        [interviews]
    );

    useEffect(() => {
        if (!projectId) return;
        try {
            const raw = localStorage.getItem(uploadTrackingStorageKey);
            if (!raw) return;
            const payload = JSON.parse(raw) as { startedAt?: string };
            if (payload?.startedAt) {
                setMessage("Estamos procesando la entrevista en segundo plano. Puedes seguir navegando.");
            }
        } catch {
            localStorage.removeItem(uploadTrackingStorageKey);
        }
    }, [projectId, uploadTrackingStorageKey]);

    const fetchInterviewStatuses = useCallback(async () => {
        if (!projectId) return;
        try {
            const response = await apiClient(`interviews/project/${projectId}`);
            if (response.ok) {
                const data = (await response.json()) as InterviewStatusItem[];
                const sorted = [...data].sort((a, b) => {
                    const aTime = new Date(a.created_at || 0).getTime();
                    const bTime = new Date(b.created_at || 0).getTime();
                    return bTime - aTime;
                });
                setInterviews(sorted);

                const trackedRaw = localStorage.getItem(uploadTrackingStorageKey);
                if (!trackedRaw) return;
                let tracked: { interviewId?: string };
                try {
                    tracked = JSON.parse(trackedRaw) as { interviewId?: string };
                } catch {
                    localStorage.removeItem(uploadTrackingStorageKey);
                    return;
                }
                if (!tracked?.interviewId) return;
                const trackedInterview = sorted.find((item) => item.id === tracked.interviewId);
                if (!trackedInterview) return;
                const status = (trackedInterview.transcription_status || "").toLowerCase();
                if (status === "completed") {
                    setMessage("Transcripción completada. Ya puedes generar la teorización.");
                    localStorage.removeItem(uploadTrackingStorageKey);
                } else if (status === "failed") {
                    setMessage("La transcripción falló. Revisa el archivo o vuelve a subir la entrevista.");
                    localStorage.removeItem(uploadTrackingStorageKey);
                }
            }
        } catch (error) {
            console.error("Error fetching interview statuses:", error);
        }
    }, [projectId, uploadTrackingStorageKey]);

    useEffect(() => {
        void fetchInterviewStatuses();
    }, [fetchInterviewStatuses]);

    useEffect(() => {
        if (!projectId) return;
        const intervalId = setInterval(() => {
            void fetchInterviewStatuses();
        }, 7000);
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
            const response = await apiClient(`interviews/upload?project_id=${projectId}`, {
                method: "POST",
                body: formData,
            });

            if (response.ok) {
                const created = (await response.json()) as InterviewStatusItem;
                localStorage.setItem(
                    uploadTrackingStorageKey,
                    JSON.stringify({
                        interviewId: created.id,
                        startedAt: new Date().toISOString(),
                    })
                );
                setMessage("Archivo recibido. Iniciamos la transcripción y puede tardar varios minutos.");
                setFile(null);
                setPseudonym("");
                await fetchInterviewStatuses();
                onUploadSuccess();
            } else {
                const err = await response.json();
                setMessage(`Error: ${err.detail || "Error desconocido"}`);
            }
        } catch (error) {
            console.error("Upload failed", error);
            setMessage("Error de conexion con el servidor.");
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="rounded-3xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-zinc-900/50">
            <h3 className="mb-2 text-xl font-bold dark:text-white">Subir Entrevista</h3>
            <p className="mb-4 text-sm text-zinc-500">
                Flujo recomendado: subir entrevista, esperar transcripción completa y luego generar teorización.
            </p>
            <form onSubmit={handleUpload} className="space-y-4">
                <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-600 dark:text-zinc-300">Seudónimo del participante (opcional)</label>
                    <input
                        type="text"
                        value={pseudonym}
                        onChange={(event) => setPseudonym(event.target.value)}
                        placeholder="Ej: Participante A"
                        className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-600 dark:border-zinc-800 dark:bg-zinc-950"
                    />
                </div>
                <div>
                    <label htmlFor={`interview-file-${projectId}`} className="mb-1 block text-sm font-medium text-zinc-600 dark:text-zinc-300">Archivo de audio o transcripción</label>
                    <input
                        id={`interview-file-${projectId}`}
                        name="file"
                        type="file"
                        accept="audio/*,text/plain,application/json"
                        title="Selecciona un archivo de audio o una transcripción"
                        aria-label="Archivo de audio o transcripción"
                        onChange={(event) => setFile(event.target.files?.[0] || null)}
                        className="block w-full text-sm text-zinc-600 dark:text-zinc-300 file:mr-4 file:rounded-xl file:border-0 file:bg-indigo-600 file:px-4 file:py-2 file:text-sm file:font-bold file:text-white hover:file:bg-indigo-700"
                    />
                </div>
                <button
                    type="submit"
                    disabled={uploading || !file}
                    className="w-full rounded-2xl bg-indigo-600 py-4 font-bold text-white transition-all hover:bg-indigo-700 disabled:opacity-50 active:scale-95"
                >
                    {uploading ? "Subiendo archivo..." : "Iniciar procesamiento"}
                </button>

                {message && (
                    <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-sm font-medium text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
                        {message}
                    </div>
                )}

                {interviews.length > 0 && (
                    <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-950">
                        <div className="mb-2 flex items-center justify-between gap-3">
                            <p className="text-xs font-bold uppercase tracking-wide text-zinc-600 dark:text-zinc-300">Estado de procesamiento</p>
                            {processingCount > 0 && (
                                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                                    {processingCount} en curso
                                </span>
                            )}
                        </div>

                        <div className="space-y-2">
                            {interviews.slice(0, 5).map((item) => {
                                const status = item.transcription_status || "unknown";
                                return (
                                    <div key={item.id} className="flex items-center justify-between gap-3 text-xs">
                                        <div className="flex items-center gap-3">
                                            <div>
                                                <p className="truncate pr-2 text-zinc-700 dark:text-zinc-300">
                                                    {item.participant_pseudonym || "Entrevista sin seudónimo"}
                                                </p>
                                                <p className="text-[10px] text-zinc-500">{formatDate(item.created_at)}</p>
                                            </div>
                                            {status === "completed" && (
                                                <button
                                                    type="button"
                                                    onClick={() => setOpenInterview(item.id)}
                                                    className="text-xs font-bold text-indigo-600"
                                                >
                                                    Ver transcripción
                                                </button>
                                            )}
                                        </div>
                                        <span className={`rounded-full px-2 py-0.5 font-medium ${getStatusTone(status)}`}>
                                            {getStatusLabel(status)}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>

                        {processingCount > 0 && (
                            <p className="mt-3 text-[11px] text-zinc-500">
                                Puedes cambiar de pestaña: el procesamiento continúa en segundo plano.
                            </p>
                        )}
                    </div>
                )}

                {openInterview && (
                    <InterviewModal interviewId={openInterview} projectId={projectId} onClose={() => setOpenInterview(null)} />
                )}
            </form>
        </div>
    );
}
