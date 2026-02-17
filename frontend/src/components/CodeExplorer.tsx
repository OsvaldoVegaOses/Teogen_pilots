"use client";

import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";

interface Code {
    id: string;
    label: string;
    definition: string;
    code_type: string;
    created_by: string;
}

export default function CodeExplorer({ projectId }: { projectId: string }) {
    const [codes, setCodes] = useState<Code[]>([]);

    useEffect(() => {
        const fetchCodes = async () => {
            try {
                const res = await apiClient(`codes/project/${projectId}`);
                if (res.ok) setCodes(await res.json());
                else console.error("Failed to fetch codes:", res.status);
            } catch (e) {
                console.error("Error fetching codes:", e);
            }
        };

        if (projectId) fetchCodes();
    }, [projectId]);

    return (
        <div className="rounded-3xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-zinc-900/50 h-full overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold dark:text-white">📚 Libro de Códigos</h3>
                <span className="text-sm text-zinc-500 font-medium">{codes.length} códigos</span>
            </div>

            <div className="space-y-3">
                {codes.map(code => (
                    <div key={code.id} className="group flex items-center justify-between rounded-xl border border-zinc-100 p-4 transition-all hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
                        <div>
                            <h4 className="font-bold text-sm dark:text-white">{code.label}</h4>
                            <p className="text-xs text-zinc-500 line-clamp-1">{code.definition || "Sin definición conceptual"}</p>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${code.created_by === 'ai' ? 'bg-purple-100 text-purple-600' : 'bg-green-100 text-green-600'}`}>
                                {code.created_by}
                            </span>
                            <button className="opacity-0 group-hover:opacity-100 transition-opacity text-xs text-indigo-600 font-bold">Ver</button>
                        </div>
                    </div>
                ))}
                {codes.length === 0 && (
                    <div className="py-20 text-center">
                        <p className="text-zinc-400 text-sm">No se han extraído códigos todavía.</p>
                        <p className="text-[10px] text-zinc-500 mt-2">La IA generará códigos a medida que transcribas entrevistas.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
