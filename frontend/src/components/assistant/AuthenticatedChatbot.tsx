"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

const quickPrompts = [
  "Como usar codificacion abierta, axial y selectiva?",
  "Buenas practicas para teoria trazable por claim",
  "Que revisar antes de exportar un reporte?",
  "Contacto comercial",
];

export default function AuthenticatedChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [metrics, setMetrics] = useState<{ total_messages_7d: number; blocked_messages_7d: number; leads_7d: number } | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome-auth",
      role: "assistant",
      text: "Asistente tecnico de TheoGen. Te ayudo en uso funcional de la plataforma sin exponer codigo ni datos internos.",
    },
  ]);

  const canSend = useMemo(() => input.trim().length > 0, [input]);

  useEffect(() => {
    let mounted = true;
    async function loadMetrics() {
      try {
        const response = await apiClient("/assistant/authenticated/metrics", { method: "GET" });
        if (!response.ok) return;
        const payload = (await response.json()) as {
          logging_enabled: boolean;
          total_messages_7d: number;
          blocked_messages_7d: number;
          leads_7d: number;
        };
        if (mounted && payload.logging_enabled) {
          setMetrics({
            total_messages_7d: payload.total_messages_7d,
            blocked_messages_7d: payload.blocked_messages_7d,
            leads_7d: payload.leads_7d,
          });
        }
      } catch {
        // Keep metrics optional to avoid breaking chat UX.
      }
    }
    void loadMetrics();
    return () => {
      mounted = false;
    };
  }, []);

  async function askAssistant(rawMessage: string) {
    const clean = rawMessage.trim();
    if (!clean) return;

    const userMessage: ChatMessage = {
      id: `auth-user-${Date.now()}`,
      role: "user",
      text: clean,
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsSending(true);

    try {
      const response = await apiClient("/assistant/authenticated/chat", {
        method: "POST",
        body: JSON.stringify({ message: clean, session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = (await response.json()) as { session_id: string; reply: string };
      if (payload?.session_id) {
        setSessionId(payload.session_id);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `auth-assistant-${Date.now() + 1}`,
          role: "assistant",
          text: payload.reply || "No pude responder ahora. Intenta reformular la pregunta.",
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `auth-assistant-error-${Date.now() + 1}`,
          role: "assistant",
          text: "No pude responder en este momento. Reintenta en unos segundos.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const clean = input.trim();
    if (!clean || isSending) return;
    setInput("");
    await askAssistant(clean);
  }

  async function onQuickPrompt(prompt: string) {
    if (isSending) return;
    setIsOpen(true);
    await askAssistant(prompt);
  }

  return (
    <div className="fixed bottom-5 right-5 z-[70]">
      {isOpen ? (
        <div className="w-[min(92vw,360px)] overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <div>
              <p className="text-sm font-semibold">Asistente tecnico</p>
              <p className="text-xs text-zinc-500">Modo usuario logeado</p>
              {metrics && (
                <p className="mt-1 text-[10px] text-zinc-500">
                  7d: {metrics.total_messages_7d} mensajes | {metrics.blocked_messages_7d} bloqueados | {metrics.leads_7d} leads
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-900"
              aria-label="Cerrar chat tecnico"
            >
              Cerrar
            </button>
          </div>

          <div className="max-h-[360px] space-y-3 overflow-y-auto px-4 py-3">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "assistant" ? "text-left" : "text-right"}>
                <p
                  className={
                    m.role === "assistant"
                      ? "inline-block max-w-[90%] rounded-xl bg-zinc-100 px-3 py-2 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                      : "inline-block max-w-[90%] rounded-xl bg-indigo-600 px-3 py-2 text-xs text-white"
                  }
                >
                  {m.text}
                </p>
              </div>
            ))}
          </div>

          <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <div className="mb-3 flex flex-wrap gap-2">
              {quickPrompts.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => onQuickPrompt(p)}
                  className="rounded-full border border-zinc-200 px-3 py-1 text-[11px] text-zinc-600 hover:border-indigo-300 hover:text-indigo-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-700 dark:hover:text-indigo-300"
                >
                  {p}
                </button>
              ))}
            </div>
            <form onSubmit={onSubmit} className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Pregunta tecnica de uso..."
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 placeholder:text-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-950"
              />
              <button
                type="submit"
                disabled={!canSend || isSending}
                className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSending ? "..." : "Enviar"}
              </button>
            </form>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="rounded-full bg-indigo-700 px-4 py-3 text-sm font-semibold text-white shadow-lg transition-colors hover:bg-indigo-800"
          aria-label="Abrir asistente tecnico"
        >
          Asistente tecnico
        </button>
      )}
    </div>
  );
}
