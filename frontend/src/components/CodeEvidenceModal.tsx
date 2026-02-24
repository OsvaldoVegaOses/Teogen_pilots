"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import InterviewModal from "./InterviewModal";

export default function CodeEvidenceModal({ codeId, projectId, onClose }: { codeId: string | null, projectId?: string | null, onClose: () => void }) {
    const [loading, setLoading] = useState(false);
    const [items, setItems] = useState<any[]>([]);
    const [page, setPage] = useState(1);
    const [hasNext, setHasNext] = useState(false);
    const [openInterview, setOpenInterview] = useState<string | null>(null);

    useEffect(() => {
        if (!codeId) return;
        setLoading(true);
        const load = async () => {
            try {
                const resp = await apiClient(`codes/${codeId}/evidence?page=${page}&page_size=20`);
                if (!resp.ok) {
                    setItems([]);
                    setHasNext(false);
                    return;
                }
                const data = await resp.json();
                setItems(data.items || []);
                setHasNext(Boolean(data.pagination?.has_next));
            } catch (e) {
                console.error(e);
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [codeId, page]);

    if (!codeId) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="fixed inset-0 bg-black/40" onClick={onClose} />
            <div className="relative w-[95%] max-w-4xl bg-white rounded-xl p-6 shadow-xl dark:bg-zinc-900 dark:border dark:border-zinc-800">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-bold">Evidencia del Código</h3>
                    <div className="flex gap-2">
                        <button onClick={onClose} className="rounded-xl bg-zinc-100 px-3 py-1 text-sm">Cerrar</button>
                    </div>
                </div>

                {loading ? (
                    <p>Cargando...</p>
                ) : (
                    <div className="space-y-3 max-h-80 overflow-y-auto">
                        {items.map((it) => (
                            <div key={it.link_id} className="rounded-lg border p-3 flex justify-between">
                                <div>
                                    <div className="text-xs text-zinc-500">{it.interview?.participant_pseudonym || 'Sin seudónimo'} · {it.fragment?.paragraph_index != null ? `p:${it.fragment.paragraph_index}` : ''}</div>
                                    <div className="text-sm text-zinc-700 dark:text-zinc-200 whitespace-pre-wrap break-words">{it.fragment?.text}</div>
                                </div>
                                <div className="flex flex-col gap-2 ml-4">
                                    <div className="flex flex-col gap-2">
                                        <button onClick={() => setOpenInterview(it.interview?.id)} className="rounded-xl border px-3 py-1 text-sm">Ver entrevista</button>
                                        <button onClick={() => {
                                            // scroll to fragment in interview modal via props
                                            setOpenInterview(it.interview?.id);
                                            setTimeout(() => {
                                                const el = document.querySelector(`[data-fragment-id="${it.fragment?.id}"]`);
                                                if (el) (el as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' });
                                            }, 600);
                                        }} className="rounded-xl border px-3 py-1 text-sm">Ver en contexto</button>
                                        <button onClick={() => {
                                            // open TheoryViewer: scroll to theory-viewer and set localStorage highlight
                                            try { localStorage.setItem('theogen_highlight_fragment', it.fragment?.id || ''); } catch {}
                                            document.getElementById('theory-viewer')?.scrollIntoView({ behavior: 'smooth' });
                                            onClose();
                                        }} className="rounded-xl border px-3 py-1 text-sm">Abrir en Teoría</button>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {items.length === 0 && <p className="text-sm text-zinc-500">No hay evidencia para este código.</p>}
                    </div>
                )}

                <div className="mt-4 flex justify-between">
                    <div>
                        <button disabled={page<=1} onClick={() => setPage(p => Math.max(1, p-1))} className="px-3 py-1 rounded-xl border mr-2">Anterior</button>
                        <button disabled={!hasNext} onClick={() => setPage(p => p+1)} className="px-3 py-1 rounded-xl border">Siguiente</button>
                    </div>
                </div>

                {openInterview && (
                    <InterviewModal interviewId={openInterview} projectId={projectId} onClose={() => setOpenInterview(null)} />
                )}
            </div>
        </div>
    );
}
