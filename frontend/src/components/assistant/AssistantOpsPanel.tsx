"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

type AssistantMessageLogItem = {
  session_id: string;
  mode: string;
  user_message: string;
  assistant_reply: string;
  intent: string;
  blocked: boolean;
  created_at: string;
};

type AssistantLeadItem = {
  session_id: string;
  source_mode: string;
  name: string;
  email: string;
  company?: string | null;
  phone?: string | null;
  created_at: string;
};

export default function AssistantOpsPanel() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loggingEnabled, setLoggingEnabled] = useState(false);
  const [messages, setMessages] = useState<AssistantMessageLogItem[]>([]);
  const [leads, setLeads] = useState<AssistantLeadItem[]>([]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await apiClient("/assistant/authenticated/ops");
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = (await response.json()) as {
          logging_enabled: boolean;
          recent_messages: AssistantMessageLogItem[];
          recent_leads: AssistantLeadItem[];
        };
        if (!mounted) return;
        setLoggingEnabled(Boolean(payload.logging_enabled));
        setMessages(payload.recent_messages || []);
        setLeads(payload.recent_leads || []);
      } catch {
        if (!mounted) return;
        setError("No fue posible cargar operaciones del asistente.");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-3xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900/50">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold dark:text-white">Mensajes recientes</h3>
          <span className="text-xs text-zinc-500">{loggingEnabled ? "logging activo" : "logging inactivo"}</span>
        </div>
        {loading && <p className="mt-4 text-sm text-zinc-500">Cargando...</p>}
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
        {!loading && !error && messages.length === 0 && (
          <p className="mt-4 text-sm text-zinc-500">No hay mensajes registrados.</p>
        )}
        <div className="mt-4 space-y-3">
          {messages.map((item, index) => (
            <article key={`${item.session_id}-${index}`} className="rounded-2xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
              <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                <span>{item.mode}</span>
                <span>{item.intent}</span>
                {item.blocked && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">blocked</span>}
              </div>
              <p className="font-semibold text-zinc-800 dark:text-zinc-100">{item.user_message}</p>
              <p className="mt-2 text-zinc-600 dark:text-zinc-300">{item.assistant_reply}</p>
              <p className="mt-2 text-[11px] text-zinc-400">{item.created_at}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-3xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900/50">
        <h3 className="text-lg font-bold dark:text-white">Leads recientes</h3>
        {loading && <p className="mt-4 text-sm text-zinc-500">Cargando...</p>}
        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
        {!loading && !error && leads.length === 0 && (
          <p className="mt-4 text-sm text-zinc-500">No hay leads registrados.</p>
        )}
        <div className="mt-4 space-y-3">
          {leads.map((lead, index) => (
            <article key={`${lead.session_id}-${index}`} className="rounded-2xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
              <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                <span>{lead.source_mode}</span>
                <span>{lead.created_at}</span>
              </div>
              <p className="font-semibold text-zinc-800 dark:text-zinc-100">{lead.name}</p>
              <p className="text-zinc-600 dark:text-zinc-300">{lead.email}</p>
              {lead.company && <p className="text-zinc-600 dark:text-zinc-300">{lead.company}</p>}
              {lead.phone && <p className="text-zinc-600 dark:text-zinc-300">{lead.phone}</p>}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
