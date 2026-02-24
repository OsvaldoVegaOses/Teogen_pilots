"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export default function InterviewModal({ interviewId, projectId, onClose, seekMs, highlightFragment }: { interviewId: string | null, projectId?: string | null, onClose: () => void, seekMs?: number | null, highlightFragment?: string | null }) {
    const [loading, setLoading] = useState(false);
    const [segments, setSegments] = useState<any[]>([]);
    const [page, setPage] = useState(1);
    const [hasNext, setHasNext] = useState(false);
    const [message, setMessage] = useState("");
    const [includeFull, setIncludeFull] = useState(false);
    const [query, setQuery] = useState("");
    const audioRef = useState<HTMLAudioElement | null>(null)[0] as any;

    useEffect(() => {
        if (!interviewId) return;
        setLoading(true);
        const load = async () => {
            try {
                const q = query ? `&q=${encodeURIComponent(query)}` : '';
                const full = includeFull ? `&include_full_text=true` : '';
                const resp = await apiClient(`interviews/id/${interviewId}/transcript?page=${page}&page_size=200${q}${full}`);
                if (!resp.ok) {
                    setMessage(`Error cargando transcripción: ${resp.status}`);
                    setSegments([]);
                    setHasNext(false);
                    return;
                }
                const data = await resp.json();
                setSegments(data.segments || []);
                setHasNext(Boolean(data.pagination?.has_next));

                setTimeout(() => {
                    if (highlightFragment) {
                        const el = document.querySelector(`[data-fragment-id="${highlightFragment}"]`);
                        (el as HTMLElement | null)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    } else if (seekMs != null) {
                        const el = document.querySelector(`[data-start-ms][data-start-ms<='${seekMs}']`);
                        if (el) (el as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 300);

            } catch (e) {
                console.error(e);
                setMessage("Error de conexión");
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [interviewId, page, includeFull, query, seekMs, highlightFragment]);

    async function startExport(format: "json" | "pdf") {
        if (!projectId || !interviewId) return;
        setMessage("Solicitando export...\n");
        try {
            const resp = await apiClient(`interviews/export`, {
                method: "POST",
                body: JSON.stringify({
                    project_id: projectId,
                    interview_ids: [interviewId],
                    scope: "selected",
                    format,
                    include_metadata: true,
                    include_codes: true,
                    include_timestamps: true,
                    language: "es"
                })
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                setMessage(`Error iniciando export: ${err.detail || resp.status}`);
                return;
            }
            const data = await resp.json();
            const taskId = data.task_id;
            setMessage(`Export encolado (task ${taskId}), esperando resultado...`);

            // Poll status
            let attempts = 0;
            const maxAttempts = 60;
            while (attempts++ < maxAttempts) {
                await new Promise(r => setTimeout(r, 1500));
                try {
                    const sresp = await apiClient(`interviews/export/status/${taskId}`);
                    if (!sresp.ok) continue;
                    const sdata = await sresp.json();
                    if (sdata.status === "completed" && sdata.result?.download_url) {
                        window.open(sdata.result.download_url, "_blank");
                        setMessage("Export listo — se abrió el enlace de descarga.");
                        return;
                    }
                    if (sdata.status === "failed") {
                        setMessage(`Export falló: ${sdata.message || 'error'}`);
                        return;
                    }
                } catch (e) {
                    console.warn(e);
                }
            }
            setMessage("Export en proceso. Revisa la sección de exportaciones más tarde.");
        } catch (e) {
            console.error(e);
            setMessage("Error iniciando export");
        }
    }

    if (!interviewId) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="fixed inset-0 bg-black/40" onClick={onClose} />
            <div className="relative w-[90%] max-w-3xl bg-white rounded-xl p-6 shadow-xl dark:bg-zinc-900 dark:border dark:border-zinc-800">
                <div className="flex justify-between items-start mb-4">
                    <h3 className="text-lg font-bold">Transcripción — {interviewId}</h3>
                    <div className="flex gap-2 items-center">
                        <input id="includeFull" type="checkbox" checked={includeFull} onChange={() => { setIncludeFull(f => !f); setPage(1); }} />
                        <label htmlFor="includeFull" className="text-sm mr-3">Incluir texto completo</label>
                        <input placeholder="Buscar en transcripción" value={query} onChange={(e) => setQuery(e.target.value)} className="rounded-xl border px-2 py-1 text-sm mr-2" />
                        <button onClick={() => startExport("json")} className="rounded-xl border px-3 py-1 text-sm">Exportar JSON</button>
                        <button onClick={() => startExport("pdf")} className="rounded-xl border px-3 py-1 text-sm">Exportar PDF</button>
                        <button onClick={onClose} className="rounded-xl bg-zinc-100 px-3 py-1 text-sm">Cerrar</button>
                    </div>
                </div>

                {message && <div className="mb-3 text-sm whitespace-pre-wrap text-zinc-600">{message}</div>}

                {loading ? (
                    <p>Cargando...</p>
                ) : (
                    <div className="space-y-3 max-h-80 overflow-y-auto">
                        {segments.map((s) => (
                            <div key={s.fragment_id} data-fragment-id={s.fragment_id} data-start-ms={s.start_ms} className={`rounded-lg border p-3 ${highlightFragment === s.fragment_id ? 'ring-2 ring-indigo-400' : ''}`}>
                                <div className="flex justify-between items-start">
                                    <div className="text-xs text-zinc-500 mb-1">{s.speaker_id} · {s.start_ms ? `${Math.round(s.start_ms/1000)}s` : ''}</div>
                                    <div className="flex gap-2">
                                        {s.start_ms != null && (
                                            <button onClick={() => {
                                                const audio = document.querySelector<HTMLAudioElement>(`audio[data-interview-id="${interviewId}"]`);
                                                if (audio) {
                                                    audio.currentTime = (s.start_ms || 0) / 1000;
                                                    audio.play().catch(() => {});
                                                }
                                            }} className="text-xs text-indigo-600">Ver en contexto</button>
                                        )}
                                    </div>
                                </div>
                                <div className="text-sm text-zinc-700 dark:text-zinc-200 whitespace-pre-wrap break-words">{s.text}</div>
                            </div>
                        ))}
                        {segments.length === 0 && <p className="text-sm text-zinc-500">No hay segmentos disponibles.</p>}
                    </div>
                )}

                <div className="mt-4 flex justify-between items-center">
                    <div>
                        <button disabled={page<=1} onClick={() => setPage(p => Math.max(1, p-1))} className="px-3 py-1 rounded-xl border mr-2">Anterior</button>
                        <button disabled={!hasNext} onClick={() => setPage(p => p+1)} className="px-3 py-1 rounded-xl border">Siguiente</button>
                    </div>
                    <div>
                        <audio data-interview-id={interviewId} ref={(el) => { if (el) (audioRef as any) = el; }} controls className="max-w-sm" />
                    </div>
                </div>
            </div>
        </div>
    );
}
