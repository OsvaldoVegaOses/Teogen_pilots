"use client";

import { FormEvent, useMemo, useState } from "react";
import { publicApiClient } from "@/lib/api";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

const quickPrompts = [
  "Que es TheoGen?",
  "Para que industrias sirve?",
  "Como puedo empezar?",
  "Cual es el contacto comercial?",
];

function buildFallbackReply(input: string): string {
  const q = input.toLowerCase();

  const blockedPatterns = [
    "codigo fuente",
    "source code",
    "repositorio",
    "git",
    "token",
    "password",
    "clave",
    "secret",
    "base de datos interna",
    "datos del proyecto",
    "credenciales",
    ".env",
  ];

  if (blockedPatterns.some((p) => q.includes(p))) {
    return "No puedo compartir codigo fuente, credenciales, configuraciones internas ni datos privados del proyecto. Puedo ayudarte con informacion publica de TheoGen y canales formales de contacto.";
  }

  if (q.includes("contacto") || q.includes("email") || q.includes("correo") || q.includes("comercial")) {
    return "Contacto empresarial: axial@nubeweb.cl y theogen@nubeweb.cl. Sitio: https://axial.nubeweb.cl. Referente: Osvaldo Vega Oses, Sociologo.";
  }

  if (q.includes("que es") || q.includes("theogen") || q.includes("plataforma")) {
    return "TheoGen es una plataforma corporativa de insights cualitativos trazables. Convierte entrevistas y evidencia de campo en conclusiones accionables y defendibles para toma de decisiones.";
  }

  if (q.includes("industria") || q.includes("segmento") || q.includes("para quien")) {
    return "TheoGen esta pensado para educacion, ONG, estudios de mercado, empresas B2C, consultorias y sector publico.";
  }

  if (q.includes("como funciona") || q.includes("flujo") || q.includes("pasos")) {
    return "Flujo general: 1) centralizar entrevistas, 2) detectar patrones, 3) recuperar evidencia relevante, 4) generar conclusiones trazables por claim.";
  }

  if (q.includes("precio") || q.includes("plan") || q.includes("demo") || q.includes("probar")) {
    return "Para una demo o evaluacion comercial, te recomiendo escribir a axial@nubeweb.cl o theogen@nubeweb.cl. Tambien puedes iniciar una prueba desde el boton 'Probar gratis'.";
  }

  if (q.includes("seguridad") || q.includes("privacidad") || q.includes("datos")) {
    return "Este asistente de landing solo entrega informacion publica. No expone codigo, secretos, ni datos internos del proyecto.";
  }

  return "Puedo ayudarte con informacion publica de la landing: propuesta de valor, segmentos, forma de uso y contacto comercial. Si quieres, pregunta por 'contacto', 'como funciona' o 'industrias'.";
}

export default function LandingChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [leadName, setLeadName] = useState("");
  const [leadEmail, setLeadEmail] = useState("");
  const [leadCompany, setLeadCompany] = useState("");
  const [leadConsent, setLeadConsent] = useState(false);
  const [leadStatus, setLeadStatus] = useState<string | null>(null);
  const [leadSending, setLeadSending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Hola. Soy el asistente virtual de TheoGen para visitantes. Te ayudo con informacion publica de la plataforma y contacto comercial.",
    },
  ]);

  const canSend = useMemo(() => input.trim().length > 0, [input]);

  async function askAssistant(rawMessage: string) {
    const clean = rawMessage.trim();
    if (!clean) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: clean,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsSending(true);

    try {
      const response = await publicApiClient("/assistant/public/chat", {
        method: "POST",
        body: JSON.stringify({ message: clean, session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = (await response.json()) as {
        session_id: string;
        reply: string;
      };

      if (payload?.session_id) {
        setSessionId(payload.session_id);
      }

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now() + 1}`,
        role: "assistant",
        text: payload.reply || buildFallbackReply(clean),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      const assistantMessage: ChatMessage = {
        id: `assistant-fallback-${Date.now() + 1}`,
        role: "assistant",
        text: buildFallbackReply(clean),
      };
      setMessages((prev) => [...prev, assistantMessage]);
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

  async function sendQuickPrompt(prompt: string) {
    if (isSending) return;
    setIsOpen(true);
    await askAssistant(prompt);
  }

  async function submitLead(event: FormEvent) {
    event.preventDefault();
    if (leadSending) return;
    if (!sessionId) {
      setLeadStatus("Primero conversa con el asistente para iniciar la sesion.");
      return;
    }
    if (!leadConsent) {
      setLeadStatus("Debes aceptar consentimiento para registrar contacto.");
      return;
    }
    setLeadSending(true);
    setLeadStatus(null);
    try {
      const response = await publicApiClient("/assistant/public/lead", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          name: leadName,
          email: leadEmail,
          company: leadCompany || null,
          consent: leadConsent,
        }),
      });
      const payload = (await response.json()) as { created?: boolean; message?: string };
      setLeadStatus(payload.message || (payload.created ? "Contacto enviado." : "No fue posible registrar contacto."));
      if (payload.created) {
        setLeadName("");
        setLeadEmail("");
        setLeadCompany("");
        setLeadConsent(false);
      }
    } catch {
      setLeadStatus("No fue posible registrar tu contacto en este momento.");
    } finally {
      setLeadSending(false);
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-[60]">
      {isOpen ? (
        <div className="w-[min(92vw,340px)] overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <div>
              <p className="text-sm font-semibold">Asistente virtual</p>
              <p className="text-xs text-zinc-500">Solo informacion publica</p>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-900"
              aria-label="Cerrar chat"
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
                      ? "inline-block max-w-[88%] rounded-xl bg-zinc-100 px-3 py-2 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                      : "inline-block max-w-[88%] rounded-xl bg-indigo-600 px-3 py-2 text-xs text-white"
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
                  onClick={() => sendQuickPrompt(p)}
                  className="rounded-full border border-zinc-200 px-3 py-1 text-[11px] text-zinc-600 hover:border-indigo-300 hover:text-indigo-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-700 dark:hover:text-indigo-300"
                >
                  {p}
                </button>
              ))}
            </div>

            <form onSubmit={submitLead} className="mb-3 space-y-2 rounded-lg border border-zinc-200 p-2 dark:border-zinc-700">
              <p className="text-[11px] font-semibold text-zinc-600 dark:text-zinc-300">Quieres que te contactemos?</p>
              <input
                value={leadName}
                onChange={(e) => setLeadName(e.target.value)}
                required
                placeholder="Nombre"
                className="w-full rounded border border-zinc-300 px-2 py-1.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-950"
              />
              <input
                value={leadEmail}
                onChange={(e) => setLeadEmail(e.target.value)}
                required
                type="email"
                placeholder="Email"
                className="w-full rounded border border-zinc-300 px-2 py-1.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-950"
              />
              <input
                value={leadCompany}
                onChange={(e) => setLeadCompany(e.target.value)}
                placeholder="Empresa (opcional)"
                className="w-full rounded border border-zinc-300 px-2 py-1.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-950"
              />
              <label className="flex items-center gap-2 text-[11px] text-zinc-600 dark:text-zinc-300">
                <input type="checkbox" checked={leadConsent} onChange={(e) => setLeadConsent(e.target.checked)} />
                Acepto compartir mis datos de contacto.
              </label>
              <button
                type="submit"
                disabled={leadSending}
                className="w-full rounded bg-zinc-900 px-2 py-1.5 text-[11px] font-semibold text-white disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900"
              >
                {leadSending ? "Enviando..." : "Solicitar contacto"}
              </button>
              {leadStatus && <p className="text-[11px] text-zinc-500">{leadStatus}</p>}
            </form>

            <form onSubmit={onSubmit} className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Escribe tu pregunta..."
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
          className="rounded-full bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg transition-colors hover:bg-indigo-700"
          aria-label="Abrir asistente virtual"
        >
          Asistente virtual
        </button>
      )}
    </div>
  );
}
