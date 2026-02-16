"use client";

import { useState } from "react";
import Link from "next/link";
import InterviewUpload from "@/components/InterviewUpload";
import MemoManager from "@/components/MemoManager";
import CodeExplorer from "@/components/CodeExplorer";

export default function Dashboard() {
    const [projects] = useState([
        { id: "123e4567-e89b-12d3-a456-426614174000", name: "Impacto del Cambio Climático", interviews: 12, status: "Teorización", progress: 85 },
        { id: "2", name: "Organización Comunitaria", interviews: 8, status: "Codificación", progress: 45 },
    ]);

    const [selectedProjectId, setSelectedProjectId] = useState<string | null>(projects[0].id);
    const [activeTab, setActiveTab] = useState<"overview" | "codes" | "memos">("overview");

    return (
        <div className="flex h-screen bg-zinc-50 dark:bg-black overflow-hidden">
            {/* Sidebar */}
            <aside className="w-64 border-r border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950 shrink-0">
                <div className="flex items-center gap-2 mb-10">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">
                        T
                    </div>
                    <span className="text-xl font-bold tracking-tight dark:text-white">TheoGen</span>
                </div>
                <nav className="flex flex-col gap-2">
                    <button
                        onClick={() => setActiveTab("overview")}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'overview' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'}`}
                    >
                        📊 Dashboard
                    </button>
                    <button
                        onClick={() => setActiveTab("codes")}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'codes' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'}`}
                    >
                        📚 Libro de Códigos
                    </button>
                    <button
                        onClick={() => setActiveTab("memos")}
                        className={`flex items-center gap-3 rounded-xl p-3 font-medium transition-colors ${activeTab === 'memos' ? 'bg-zinc-100 text-indigo-600 dark:bg-zinc-900/50' : 'text-zinc-500 hover:bg-zinc-100'}`}
                    >
                        📝 Memos
                    </button>
                </nav>
            </aside>

            {/* Main Content Area */}
            <main className="flex-1 flex flex-col min-w-0">
                <header className="flex items-center justify-between p-8 border-b border-zinc-100 bg-white/50 backdrop-blur-sm dark:bg-zinc-950/50 dark:border-zinc-800">
                    <div>
                        <h1 className="text-2xl font-bold dark:text-white">
                            {activeTab === "overview" && "Panel de Control"}
                            {activeTab === "codes" && "Exploración de Conceptos"}
                            {activeTab === "memos" && "Memos Analíticos"}
                        </h1>
                    </div>
                    <div className="flex gap-4">
                        <button className="rounded-2xl border border-zinc-200 px-6 py-2 text-sm font-bold hover:bg-zinc-50 transition-all dark:border-zinc-800 dark:text-white">
                            Sincronizar Cloud
                        </button>
                        <button className="rounded-2xl bg-indigo-600 px-6 py-2 text-sm font-bold text-white hover:bg-indigo-700 transition-all">
                            + Nuevo Proyecto
                        </button>
                    </div>
                </header>

                <div className="flex-1 p-8 overflow-y-auto">
                    {activeTab === "overview" && (
                        <div className="grid gap-10 lg:grid-cols-3">
                            <div className="lg:col-span-2 grid gap-6 md:grid-cols-2 self-start">
                                {projects.map((project) => (
                                    <div
                                        key={project.id}
                                        onClick={() => setSelectedProjectId(project.id)}
                                        className={`cursor-pointer group relative rounded-3xl border p-8 transition-all hover:shadow-xl ${selectedProjectId === project.id ? 'border-indigo-600 bg-white ring-2 ring-indigo-600/10' : 'border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/50'}`}
                                    >
                                        <div className="flex items-start justify-between mb-4">
                                            <span className="text-xs font-bold uppercase tracking-widest text-indigo-600">{project.status}</span>
                                            <span className="text-2xl">📁</span>
                                        </div>
                                        <h3 className="text-xl font-bold dark:text-white">{project.name}</h3>
                                        <p className="mt-2 text-sm text-zinc-500">{project.interviews} entrevistas codificadas</p>

                                        <div className="mt-6">
                                            <div className="flex justify-between text-xs font-bold mb-2 dark:text-zinc-400">
                                                <span>Progreso de Saturación</span>
                                                <span>{project.progress}%</span>
                                            </div>
                                            <div className="h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
                                                <div
                                                    className="h-full rounded-full bg-indigo-600 transition-all duration-1000 shadow-[0_0_10px_rgba(79,70,229,0.5)]"
                                                    style={{ width: `${project.progress}%` }}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div className="space-y-6">
                                {selectedProjectId ? (
                                    <InterviewUpload
                                        projectId={selectedProjectId}
                                        onUploadSuccess={() => console.log("Refresh list...")}
                                    />
                                ) : (
                                    <div className="p-8 text-center border-2 border-dashed rounded-3xl border-zinc-200">
                                        <p className="text-zinc-400">Selecciona un proyecto para subir entrevistas.</p>
                                    </div>
                                )}

                                <div className="rounded-3xl bg-indigo-600 p-8 text-white shadow-xl shadow-indigo-500/20">
                                    <h4 className="font-bold mb-2 text-lg">Teorización Assist</h4>
                                    <p className="text-white/80 text-sm mb-6">Analiza las {projects.find(p => p.id === selectedProjectId)?.interviews} entrevistas para buscar patrones emergentes.</p>
                                    <button
                                        className="w-full rounded-xl bg-white py-3 text-sm font-bold text-indigo-600 shadow-lg transition-all hover:scale-102 hover:bg-indigo-50 active:scale-98"
                                        onClick={() => alert("GPT-5.2 está analizando los fragmentos...")}
                                    >
                                        Generar Teoría (v1.2)
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === "codes" && selectedProjectId && (
                        <div className="h-full">
                            <CodeExplorer projectId={selectedProjectId} />
                        </div>
                    )}

                    {activeTab === "memos" && selectedProjectId && (
                        <div className="max-w-4xl mx-auto">
                            <MemoManager projectId={selectedProjectId} />
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
