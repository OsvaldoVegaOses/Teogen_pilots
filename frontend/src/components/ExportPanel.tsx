"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

type TaskRecord = { task_id: string, created_at: string };
type ExportStatus = {
    status?: string;
    result?: { download_url?: string };
};

function loadTasks(): TaskRecord[] {
    try {
        const raw = localStorage.getItem('export_tasks');
        if (!raw) return [];
        return JSON.parse(raw) as TaskRecord[];
    } catch { return []; }
}

function saveTask(t: TaskRecord) {
    const cur = loadTasks();
    cur.unshift(t);
    localStorage.setItem('export_tasks', JSON.stringify(cur.slice(0, 50)));
}

export default function ExportPanel({ projectId: _projectId }: { projectId?: string | null }) {
    void _projectId;
    const [tasks] = useState<TaskRecord[]>(loadTasks());
    const [statuses, setStatuses] = useState<Record<string, ExportStatus>>({});

    useEffect(() => {
        const iv = setInterval(() => {
            tasks.forEach(async (t) => {
                try {
                    const resp = await apiClient(`interviews/export/status/${t.task_id}`);
                    if (resp.ok) {
                        const data = await resp.json();
                        setStatuses(s => ({ ...s, [t.task_id]: data }));
                    }
                } catch { }
            });
        }, 3000);
        return () => clearInterval(iv);
    }, [tasks]);

    async function checkTask(task_id: string) {
        try {
            const resp = await apiClient(`interviews/export/status/${task_id}`);
            if (!resp.ok) return;
            const data = await resp.json();
            setStatuses(s => ({ ...s, [task_id]: data }));
        } catch {}
    }

    return (
        <div className="rounded-xl border p-4 bg-white dark:bg-zinc-900">
            <h4 className="font-bold mb-2">Exportaciones recientes</h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
                {tasks.length === 0 && <p className="text-sm text-zinc-600 dark:text-zinc-300">No hay exportaciones en el historial.</p>}
                {tasks.map(t => {
                    const s = statuses[t.task_id];
                    return (
                        <div key={t.task_id} className="flex items-center justify-between border rounded p-2">
                            <div className="text-xs">{t.task_id} · {new Date(t.created_at).toLocaleString()}</div>
                            <div className="flex items-center gap-2">
                                <div className="text-xs">{s?.status || 'pending'}</div>
                                {s?.result?.download_url && (
                                    <a href={s.result.download_url} target="_blank" rel="noreferrer" className="text-indigo-600 text-xs">Descargar</a>
                                )}
                                <button onClick={() => checkTask(t.task_id)} className="text-xs">Refrescar</button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export function enqueueLocalExport(task_id: string) {
    const rec = { task_id, created_at: new Date().toISOString() };
    saveTask(rec);
}
