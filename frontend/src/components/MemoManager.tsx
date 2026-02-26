"use client";

import { useState, useEffect, useCallback } from "react";
import { apiClient } from "@/lib/api";

interface Memo {
    id: string;
    title: string;
    content: string;
    memo_type: string;
    created_at: string;
}

export default function MemoManager({ projectId }: { projectId: string }) {
    const [memos, setMemos] = useState<Memo[]>([]);
    const [newTitle, setNewTitle] = useState("");
    const [newContent, setNewContent] = useState("");
    const [loading, setLoading] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");
    const [successMessage, setSuccessMessage] = useState("");

    const fetchMemos = useCallback(async () => {
        try {
            const res = await apiClient(`memos/project/${projectId}`);
            if (res.ok) {
                setMemos(await res.json());
                setErrorMessage("");
            } else {
                const err = await res.json().catch(() => ({}));
                setErrorMessage(err.detail || "No se pudieron cargar los memos.");
            }
        } catch (e) { console.error("Error fetching memos:", e); }
    }, [projectId]);

    useEffect(() => {
        if (projectId) fetchMemos();
    }, [projectId, fetchMemos]);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setErrorMessage("");
        setSuccessMessage("");
        try {
            const res = await apiClient("memos", {
                method: "POST",
                body: JSON.stringify({
                    title: newTitle,
                    content: newContent,
                    project_id: projectId
                }),
            });
            if (res.ok) {
                setNewTitle("");
                setNewContent("");
                setSuccessMessage("✅ Memo guardado correctamente.");
                fetchMemos();
            } else {
                const err = await res.json().catch(() => ({}));
                setErrorMessage(err.detail || "No se pudo guardar el memo.");
            }
        } catch (e) { console.error("Error creating memo:", e); }
        finally { setLoading(false); }
    };

    return (
        <div className="space-y-6">
            <div className="rounded-3xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-zinc-900/50">
                <h3 className="text-xl font-bold mb-4 dark:text-white">📝 Nuevo Memo Analítico</h3>
                <form onSubmit={handleCreate} className="space-y-4">
                    <input
                        type="text"
                        placeholder="Título del hallazgo"
                        value={newTitle}
                        onChange={(e) => setNewTitle(e.target.value)}
                        className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-600 dark:border-zinc-800 dark:bg-zinc-950"
                    />
                    <textarea
                        placeholder="Escribe tus reflexiones teóricas aquí..."
                        rows={4}
                        value={newContent}
                        onChange={(e) => setNewContent(e.target.value)}
                        className="w-full rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm focus:ring-2 focus:ring-indigo-600 dark:border-zinc-800 dark:bg-zinc-950"
                    />
                    <button
                        type="submit"
                        disabled={loading || !newTitle || !newContent}
                        className="w-full rounded-2xl bg-indigo-600 py-3 font-bold text-white hover:bg-indigo-700 disabled:opacity-50 transition-all"
                    >
                        {loading ? "Guardando memo..." : "Guardar Memo"}
                    </button>
                    {errorMessage && <p className="text-sm text-red-500">{errorMessage}</p>}
                    {successMessage && <p className="text-sm text-green-600">{successMessage}</p>}
                </form>
            </div>

            <div className="grid gap-4">
                {memos.map(memo => (
                    <div key={memo.id} className="rounded-2xl border border-zinc-100 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
                        <div className="flex justify-between items-start mb-2">
                            <h4 className="font-bold text-lg dark:text-white">{memo.title}</h4>
                            <span className="text-[10px] uppercase font-bold text-indigo-600 bg-indigo-50 px-2 py-1 rounded-full">
                                {memo.memo_type}
                            </span>
                        </div>
                        <p className="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-3">{memo.content}</p>
                        <p className="text-[10px] mt-4 text-zinc-400">{new Date(memo.created_at).toLocaleDateString()}</p>
                    </div>
                ))}
                {memos.length === 0 && <p className="text-center text-sm text-zinc-400 py-10">No hay memos aún.</p>}
            </div>
        </div>
    );
}
