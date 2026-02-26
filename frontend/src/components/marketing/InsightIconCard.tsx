"use client";

import { useEffect, useRef, useState } from "react";

type InsightIconType =
  | "traceability"
  | "actionable_insights"
  | "risk_control"
  | "interview_network"
  | "pattern_detection"
  | "evidence_traceability";

type InsightIconCardProps = {
  title: string;
  description: string;
  iconType: InsightIconType;
  delayMs?: number;
};

function IconTraceability() {
  return (
    <svg viewBox="0 0 64 64" className="h-12 w-12 text-indigo-500" fill="none" aria-hidden="true">
      <circle cx="12" cy="32" r="5" className="stroke-current trace-node" strokeWidth="2" />
      <circle cx="32" cy="16" r="5" className="stroke-current trace-node [animation-delay:.3s]" strokeWidth="2" />
      <circle cx="52" cy="32" r="5" className="stroke-current trace-node [animation-delay:.6s]" strokeWidth="2" />
      <circle cx="32" cy="48" r="5" className="stroke-current trace-node [animation-delay:.9s]" strokeWidth="2" />
      <path d="M17 32h10m10-13 10 9m0 8-10 9M32 21v22" className="stroke-current trace-link" strokeWidth="2" />
    </svg>
  );
}

function IconActionableInsights() {
  return (
    <svg viewBox="0 0 64 64" className="h-12 w-12 text-indigo-500" fill="none" aria-hidden="true">
      <path d="M24 42c-5-2-8-7-8-13 0-9 7-16 16-16s16 7 16 16c0 6-3 11-8 13" className="stroke-current" strokeWidth="2" />
      <rect x="24" y="44" width="16" height="8" rx="2" className="stroke-current" strokeWidth="2" />
      <path d="M20 30h8m16 0h-8M32 12v8" className="stroke-current insight-arrow" strokeWidth="2" />
      <path d="M18 22l5 5m23-5-5 5" className="stroke-current insight-arrow [animation-delay:.4s]" strokeWidth="2" />
    </svg>
  );
}

function IconRiskControl() {
  return (
    <svg viewBox="0 0 64 64" className="h-12 w-12 text-indigo-500" fill="none" aria-hidden="true">
      <path d="M32 10l18 7v14c0 12-8 20-18 23-10-3-18-11-18-23V17z" className="stroke-current" strokeWidth="2" />
      <path d="M24 32l6 6 10-10" className="stroke-current risk-check" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconInterviewNetwork() {
  return (
    <svg viewBox="0 0 64 64" className="h-12 w-12 text-indigo-500" fill="none" aria-hidden="true">
      <circle cx="20" cy="20" r="5" className="stroke-current network-node" strokeWidth="2" />
      <circle cx="44" cy="20" r="5" className="stroke-current network-node [animation-delay:.25s]" strokeWidth="2" />
      <circle cx="20" cy="44" r="5" className="stroke-current network-node [animation-delay:.5s]" strokeWidth="2" />
      <circle cx="44" cy="44" r="5" className="stroke-current network-node [animation-delay:.75s]" strokeWidth="2" />
      <path d="M25 20h14M20 25v14M44 25v14M25 44h14M24 24l16 16M40 24 24 40" className="stroke-current trace-link" strokeWidth="1.8" />
    </svg>
  );
}

function IconPatternDetection() {
  return (
    <svg viewBox="0 0 64 64" className="h-12 w-12 text-indigo-500" fill="none" aria-hidden="true">
      <circle cx="14" cy="32" r="4" className="stroke-current network-node" strokeWidth="2" />
      <circle cx="30" cy="18" r="4" className="stroke-current network-node [animation-delay:.2s]" strokeWidth="2" />
      <circle cx="30" cy="46" r="4" className="stroke-current network-node [animation-delay:.4s]" strokeWidth="2" />
      <circle cx="50" cy="32" r="4" className="stroke-current network-node [animation-delay:.6s]" strokeWidth="2" />
      <path d="M18 32h28M33 21l14 9-14 13M33 43l14-13" className="stroke-current trace-link" strokeWidth="1.8" />
    </svg>
  );
}

function IconEvidenceTraceability() {
  return (
    <svg viewBox="0 0 64 64" className="h-12 w-12 text-indigo-500" fill="none" aria-hidden="true">
      <rect x="14" y="10" width="28" height="40" rx="3" className="stroke-current" strokeWidth="2" />
      <path d="M20 20h16M20 28h16M20 36h10" className="stroke-current" strokeWidth="2" />
      <circle cx="46" cy="42" r="7" className="stroke-current doc-lens" strokeWidth="2" />
      <path d="m51 47 5 5" className="stroke-current doc-lens" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function InsightIcon({ iconType }: { iconType: InsightIconType }) {
  if (iconType === "traceability") return <IconTraceability />;
  if (iconType === "actionable_insights") return <IconActionableInsights />;
  if (iconType === "risk_control") return <IconRiskControl />;
  if (iconType === "interview_network") return <IconInterviewNetwork />;
  if (iconType === "pattern_detection") return <IconPatternDetection />;
  return <IconEvidenceTraceability />;
}

export default function InsightIconCard({ title, description, iconType, delayMs = 0 }: InsightIconCardProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
            break;
          }
        }
      },
      { threshold: 0.2 }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`insight-card rounded-3xl border border-zinc-200 p-8 transition-all hover:border-indigo-500/40 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900 ${
        visible ? "insight-card-visible" : ""
      }`}
      style={{ transitionDelay: `${Math.max(0, delayMs)}ms` }}
    >
      <div className="mb-4 flex items-center justify-center rounded-2xl border border-indigo-100/70 bg-indigo-50/60 p-3 dark:border-indigo-500/20 dark:bg-indigo-500/10">
        <InsightIcon iconType={iconType} />
      </div>
      <h3 className="text-xl font-bold">{title}</h3>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">{description}</p>
    </div>
  );
}
