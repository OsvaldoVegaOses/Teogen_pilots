from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.settings import settings
from ..models.models import Category, Code, Fragment, Interview, Project, Theory, code_fragment_links
from ..schemas.theory import TheoryGenerateRequest
from ..services.azure_openai import foundry_openai
from ..services.export.privacy import redact_pii_text
from ..services.neo4j_service import neo4j_service
from ..services.qdrant_service import qdrant_service
from ..utils.token_budget import ensure_within_budget
from .coding_engine import coding_engine
from .theory_judge import TheoryJudge, TheoryJudgeError
from .theory_engine import theory_engine

logger = logging.getLogger(__name__)


class TheoryPipelineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class StrategyState:
    max_cats: int
    max_frags_per_cat: int
    max_frag_chars: int
    max_network_top: int
    remove_evidence_step2: bool = False
    remove_evidence_step3: bool = False

    def degrade(self) -> Dict[str, Any] | None:
        if self.max_frags_per_cat > 1:
            before = self.max_frags_per_cat
            self.max_frags_per_cat -= 1
            return {"kind": "frags_per_cat", "before": before, "after": self.max_frags_per_cat}
        if self.max_frag_chars > 200:
            before = self.max_frag_chars
            self.max_frag_chars = max(200, self.max_frag_chars - 150)
            return {"kind": "frag_chars", "before": before, "after": self.max_frag_chars}
        if self.max_cats > 10:
            before = self.max_cats
            self.max_cats = max(10, self.max_cats - 10)
            return {"kind": "max_cats", "before": before, "after": self.max_cats}
        if self.max_network_top > 10:
            before = self.max_network_top
            self.max_network_top = max(10, self.max_network_top - 10)
            return {"kind": "network_top", "before": before, "after": self.max_network_top}
        if not self.remove_evidence_step2:
            self.remove_evidence_step2 = True
            return {"kind": "remove_evidence_step2", "after": True}
        if not self.remove_evidence_step3:
            self.remove_evidence_step3 = True
            return {"kind": "remove_evidence_step3", "after": True}
        return None


class TheoryPipeline:
    def __init__(self):
        self.foundry_openai = foundry_openai
        self.coding_engine = coding_engine
        self.theory_engine = theory_engine
        self.neo4j_service = neo4j_service
        self.qdrant_service = qdrant_service

    def _resolve_context_limit(self, model: str) -> int:
        model_norm = (model or "").strip().lower()
        if model_norm == "gpt-5.2-chat":
            return settings.MODEL_CONTEXT_LIMIT_GPT_52_CHAT
        return settings.MODEL_CONTEXT_LIMIT_DEFAULT

    @staticmethod
    def _log_stage(
        task_id: str,
        project_id: UUID,
        stage: str,
        started: float,
        **extra: Any,
    ) -> None:
        payload: Dict[str, Any] = {
            "task_id": task_id,
            "project_id": str(project_id),
            "stage": stage,
            "elapsed_ms": round((perf_counter() - started) * 1000.0, 2),
        }
        payload.update(extra)
        logger.info("[theory_stage] %s", payload)

    @staticmethod
    def _cats_no_evidence(cats_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {"id": c["id"], "name": c["name"], "description": c.get("description", "")}
            for c in cats_data
        ]

    @staticmethod
    def _strip_evidence_from_model_json(model_json: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(model_json, dict):
            return model_json
        cleaned: Dict[str, Any] = {}
        for key, value in model_json.items():
            key_lower = str(key).lower()
            if "evidence" in key_lower:
                continue
            if isinstance(value, dict):
                cleaned[key] = TheoryPipeline._strip_evidence_from_model_json(value)
            elif isinstance(value, list):
                cleaned[key] = [
                    TheoryPipeline._strip_evidence_from_model_json(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                cleaned[key] = value
        return cleaned

    @staticmethod
    def _slim_network_for_llm(network_metrics: Dict[str, Any], state: StrategyState) -> Dict[str, Any]:
        top_n = state.max_network_top
        return {
            "counts": network_metrics.get("counts", {}),
            "category_centrality": network_metrics.get("category_centrality", [])[:top_n],
            "category_cooccurrence": network_metrics.get("category_cooccurrence", [])[:top_n],
        }

    @staticmethod
    def _slim_cats_for_llm(
        cats_data: List[Dict[str, Any]],
        network_metrics: Dict[str, Any],
        state: StrategyState,
    ) -> List[Dict[str, Any]]:
        centrality_rank: Dict[str, int] = {
            item.get("category_id", ""): idx
            for idx, item in enumerate(network_metrics.get("category_centrality", []))
        }
        sorted_cats = sorted(cats_data, key=lambda c: centrality_rank.get(c["id"], 9999))
        result = []
        for cat in sorted_cats[: state.max_cats]:
            frags_slimmed = []
            for frag in cat.get("semantic_evidence", [])[: state.max_frags_per_cat]:
                if isinstance(frag, dict) and "text" in frag:
                    frag = {**frag, "text": str(frag.get("text", ""))[: state.max_frag_chars]}
                frags_slimmed.append(frag)
            result.append({**cat, "semantic_evidence": frags_slimmed})
        return result

    @staticmethod
    def _select_critical_subgraph(
        *,
        network_metrics: Dict[str, Any],
        top_centrality: int = 10,
        top_edges: int = 10,
        top_bridges: int = 5,
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """
        Best-effort critical subgraph selection using the metrics available today.
        - Categories: top by centrality + categories appearing in top co-occurrence edges.
        - "Bridges": proxy by edge participation frequency in the top edges.
        Returns (critical_category_ids, critical_edges[(a_id, b_id)]).
        """
        centrality = network_metrics.get("category_centrality") or []
        cooc = network_metrics.get("category_cooccurrence") or []

        critical_ids: list[str] = []
        for row in centrality[: max(0, int(top_centrality))]:
            cid = str(row.get("category_id") or "").strip()
            if cid and cid not in critical_ids:
                critical_ids.append(cid)

        edges: list[tuple[str, str]] = []
        edge_counts: dict[str, int] = {}
        for row in cooc[: max(0, int(top_edges))]:
            a = str(row.get("category_a_id") or "").strip()
            b = str(row.get("category_b_id") or "").strip()
            if not a or not b:
                continue
            edges.append((a, b))
            edge_counts[a] = edge_counts.get(a, 0) + 1
            edge_counts[b] = edge_counts.get(b, 0) + 1
            if a not in critical_ids:
                critical_ids.append(a)
            if b not in critical_ids:
                critical_ids.append(b)

        if edge_counts and top_bridges > 0:
            for cid, _cnt in sorted(edge_counts.items(), key=lambda kv: (-kv[1], kv[0]))[: int(top_bridges)]:
                if cid and cid not in critical_ids:
                    critical_ids.append(cid)

        return critical_ids, edges

    @staticmethod
    def _extract_evidence_ids(paradigm: Dict[str, Any]) -> list[str]:
        out: list[str] = []
        if not isinstance(paradigm, dict):
            return out
        for key in (
            "conditions",
            "actions",
            "consequences",
            "propositions",
            "context",
            "intervening_conditions",
        ):
            items = paradigm.get(key) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                ev = item.get("evidence_ids")
                if isinstance(ev, list):
                    for fid in ev:
                        if fid is None:
                            continue
                        s = str(fid).strip()
                        if s:
                            out.append(s)
        return out

    @staticmethod
    def _sample_evidence_diverse(
        *,
        pool: list[dict],
        fragment_to_interview: dict[str, str],
        target_max: int,
        min_interviews: int,
        max_share_per_interview: float,
    ) -> list[dict]:
        """
        Deterministic, diversity-aware sampling.
        - Round-robin across interviews.
        - Caps per-interview share when possible.
        """
        target_max = max(1, int(target_max))
        min_interviews = max(1, int(min_interviews))
        max_share_per_interview = float(max_share_per_interview)

        rows = []
        for item in pool:
            if not isinstance(item, dict):
                continue
            fid = str(item.get("fragment_id") or item.get("id") or "").strip()
            if not fid:
                continue
            try:
                score_f = float(item.get("score", 0.0))
            except Exception:
                score_f = 0.0
            rows.append({**item, "fragment_id": fid, "score": score_f})

        # Dedupe by fragment_id, keep best score.
        by_fid: dict[str, dict] = {}
        for r in rows:
            fid = r["fragment_id"]
            prev = by_fid.get(fid)
            if prev is None or float(r.get("score", 0.0)) > float(prev.get("score", 0.0)):
                by_fid[fid] = r
        rows = list(by_fid.values())

        by_iv: dict[str, list[dict]] = {}
        for r in rows:
            iv = fragment_to_interview.get(r["fragment_id"])
            if not iv:
                continue
            by_iv.setdefault(str(iv), []).append(r)

        for iv in by_iv:
            by_iv[iv] = sorted(by_iv[iv], key=lambda x: (-float(x.get("score", 0.0)), x["fragment_id"]))

        interviews = sorted(
            by_iv.keys(),
            key=lambda iv: (
                -float(by_iv[iv][0].get("score", 0.0)) if by_iv.get(iv) else 0.0,
                iv,
            ),
        )
        if not interviews:
            return []

        max_per_iv = max(1, int(target_max * max_share_per_interview))
        selected: list[dict] = []
        counts: dict[str, int] = {iv: 0 for iv in interviews}
        idx: dict[str, int] = {iv: 0 for iv in interviews}

        while len(selected) < target_max:
            progressed = False
            for iv in interviews:
                if len(selected) >= target_max:
                    break
                if counts[iv] >= max_per_iv and len(interviews) >= min_interviews:
                    continue
                items = by_iv.get(iv) or []
                j = idx[iv]
                if j >= len(items):
                    continue
                selected.append(items[j])
                idx[iv] = j + 1
                counts[iv] += 1
                progressed = True
            if not progressed:
                break

        covered = {fragment_to_interview.get(r["fragment_id"]) for r in selected if fragment_to_interview.get(r["fragment_id"])}
        if len(covered) < min_interviews:
            remaining = [r for r in rows if r["fragment_id"] not in {s["fragment_id"] for s in selected}]
            remaining = sorted(remaining, key=lambda x: (-float(x.get("score", 0.0)), x["fragment_id"]))
            for r in remaining:
                if len(selected) >= target_max:
                    break
                selected.append(r)

        return selected

    @staticmethod
    def _compute_deterministic_gaps(
        *,
        critical_category_ids: list[str],
        critical_edges: list[tuple[str, str]],
        category_by_id: dict[str, Category],
        paradigm: Dict[str, Any],
        evidence_index: list[dict],
        fragment_to_interview: dict[str, str],
        min_interviews: int,
    ) -> Dict[str, Any]:
        counts_by_iv: dict[str, int] = {}
        for ev in evidence_index:
            fid = str(ev.get("id") or ev.get("fragment_id") or "").strip()
            if not fid:
                continue
            iv = fragment_to_interview.get(fid)
            if not iv:
                continue
            counts_by_iv[iv] = counts_by_iv.get(iv, 0) + 1

        interviews_covered = len(counts_by_iv)
        total_ev = sum(counts_by_iv.values())
        top_iv_share = 0.0
        top_iv = None
        if total_ev > 0 and counts_by_iv:
            top_iv, top_cnt = sorted(counts_by_iv.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            top_iv_share = top_cnt / total_ev

        known_by_name = {
            (c.name or "").strip().lower(): str(c.id)
            for c in category_by_id.values()
            if getattr(c, "id", None) and getattr(c, "name", None)
        }
        referenced_cat_ids: set[str] = set()
        for key in ("conditions", "actions", "consequences", "context", "intervening_conditions"):
            items = paradigm.get(key) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip().lower()
                if name and name in known_by_name:
                    referenced_cat_ids.add(known_by_name[name])

        missing_cats = [cid for cid in critical_category_ids if cid not in referenced_cat_ids]

        edge_ev_counts: dict[str, int] = {}
        for ev in evidence_index:
            a = str(ev.get("edge_a_id") or "").strip()
            b = str(ev.get("edge_b_id") or "").strip()
            if not a or not b:
                continue
            k = f"{min(a, b)}::{max(a, b)}"
            edge_ev_counts[k] = edge_ev_counts.get(k, 0) + 1

        edges_without_evidence: list[dict] = []
        for a, b in critical_edges:
            k = f"{min(a, b)}::{max(a, b)}"
            if edge_ev_counts.get(k, 0) > 0:
                continue
            a_name = category_by_id.get(a).name if category_by_id.get(a) else a
            b_name = category_by_id.get(b).name if category_by_id.get(b) else b
            edges_without_evidence.append({"a_id": a, "a_name": a_name, "b_id": b, "b_name": b_name})

        gaps: list[dict] = []
        if interviews_covered < min_interviews:
            gaps.append(
                {
                    "kind": "coverage_min_interviews",
                    "message": f"Cobertura insuficiente: evidencia cita {interviews_covered} entrevistas (min={min_interviews}).",
                    "interviews_covered": interviews_covered,
                    "min_interviews": min_interviews,
                }
            )
        if top_iv_share >= 0.7 and top_iv:
            gaps.append(
                {
                    "kind": "coverage_concentration",
                    "message": "Concentracion de evidencia: una sola entrevista aporta >= 70% de las citas.",
                    "top_interview_id": top_iv,
                    "top_share": round(top_iv_share, 3),
                }
            )
        if missing_cats:
            gaps.append(
                {
                    "kind": "critical_categories_without_claims",
                    "message": "Categorias criticas (por centralidad/co-ocurrencia) no aparecen en claims del paradigma.",
                    "missing_category_ids": missing_cats[:25],
                    "missing_category_names": [
                        category_by_id[cid].name for cid in missing_cats[:25] if category_by_id.get(cid)
                    ],
                }
            )
        if edges_without_evidence:
            gaps.append(
                {
                    "kind": "strong_edges_without_evidence",
                    "message": "Co-ocurrencias/relaciones fuertes no tienen evidencia explicita recuperada.",
                    "edges": edges_without_evidence[:20],
                }
            )

        return {
            "coverage": {
                "interviews_covered": interviews_covered,
                "evidence_count": total_ev,
                "top_interview_share": round(top_iv_share, 3),
            },
            "gaps": gaps,
        }

    @staticmethod
    def _compute_max_share_per_interview(evidence_index: list[dict]) -> float:
        counts: Dict[str, int] = {}
        total = 0
        for ev in evidence_index:
            if not isinstance(ev, dict):
                continue
            iv = str(ev.get("interview_id") or "").strip()
            if not iv:
                continue
            counts[iv] = counts.get(iv, 0) + 1
            total += 1
        if total <= 0:
            return 0.0
        top = max(counts.values()) if counts else 0
        return round(top / total, 3) if top > 0 else 0.0

    async def _augment_material_evidence(
        self,
        *,
        project_id: UUID,
        owner_id: UUID,
        limit_per_query: int,
    ) -> list[dict]:
        """
        Directed retrieval for material/economic/environmental impacts.
        Used as a targeted fallback when consequences balance fails.
        """
        prompts = [
            "danos perdidas costos vivienda infraestructura salud ambiente largo plazo",
            "impacto material economico dano perdida costo reparacion",
            "afectacion ambiental y de salud consecuencias materiales",
        ]
        embeddings = await self.foundry_openai.generate_embeddings(prompts)
        if not embeddings:
            return []
        sem = asyncio.Semaphore(max(1, int(settings.THEORY_QDRANT_RETRIEVAL_CONCURRENCY)))

        async def _fetch(vec: list[float]) -> list[dict]:
            async with sem:
                return await self.qdrant_service.search_supporting_fragments(
                    project_id=project_id,
                    query_vector=vec,
                    limit=max(1, int(limit_per_query)),
                    owner_id=str(owner_id),
                )

        rows = await asyncio.gather(*[_fetch(v) for v in embeddings], return_exceptions=False)
        out: list[dict] = []
        for items in rows:
            for item in items or []:
                if isinstance(item, dict):
                    out.append(item)
        return out

    @staticmethod
    def _build_deterministic_routing_plan(
        *,
        use_subgraph_evidence: bool,
        use_model_router: bool,
        qdrant_enabled: bool,
        neo4j_enabled: bool,
    ) -> Dict[str, Any]:
        return {
            "enabled": bool(settings.THEORY_USE_DETERMINISTIC_ROUTING),
            "version": "v1",
            "plan": {
                "project_state": {"source": "postgresql", "reason": "source_of_truth"},
                "network_metrics": {
                    "primary": "neo4j",
                    "fallback": "sql",
                    "available": bool(neo4j_enabled),
                },
                "semantic_evidence": {
                    "primary": "qdrant_subgraph" if use_subgraph_evidence else "qdrant_basic",
                    "fallback": "sql",
                    "available": bool(qdrant_enabled),
                },
                "claims_traceability": {"source": "neo4j_claim_graph"},
                "judge_validation": {"source": "python_rules"},
                "llm": {
                    "identify": "reasoning_advanced",
                    "paradigm": "model_router" if use_model_router else "reasoning_advanced",
                    "gaps": "reasoning_fast",
                },
            },
            "execution": {
                "network_metrics_source": None,
                "network_metrics_fallback_reason": None,
                "semantic_evidence_source": None,
                "semantic_evidence_fallback_reason": None,
                "llm_paradigm_source": "model_router" if use_model_router else "reasoning_advanced",
            },
        }

    async def _build_sql_network_metrics_fallback(
        self,
        *,
        project_id: UUID,
        db: AsyncSession,
        categories: List[Category],
        codes: List[Code],
    ) -> Dict[str, Any]:
        """
        Deterministic SQL fallback for graph metrics when Neo4j is unavailable.
        Keeps pipeline running without blocking theory generation.
        """
        fragment_count = (
            await db.execute(
                select(func.count(Fragment.id))
                .select_from(Fragment)
                .join(Interview, Fragment.interview_id == Interview.id)
                .where(Interview.project_id == project_id)
            )
        ).scalar() or 0

        counts = {
            "category_count": len(categories or []),
            "code_count": len(codes or []),
            "fragment_count": int(fragment_count),
        }

        centrality_rows = (
            await db.execute(
                select(
                    Code.category_id,
                    func.count(func.distinct(Code.id)).label("code_degree"),
                    func.count(func.distinct(code_fragment_links.c.fragment_id)).label("fragment_degree"),
                )
                .select_from(Code)
                .outerjoin(code_fragment_links, code_fragment_links.c.code_id == Code.id)
                .where(
                    Code.project_id == project_id,
                    Code.category_id.is_not(None),
                )
                .group_by(Code.category_id)
            )
        ).all()

        agg_by_category: Dict[str, Dict[str, float]] = {}
        for category_id, code_degree, fragment_degree in centrality_rows:
            cid = str(category_id)
            agg_by_category[cid] = {
                "code_degree": float(code_degree or 0.0),
                "fragment_degree": float(fragment_degree or 0.0),
            }

        category_name_by_id = {str(c.id): c.name for c in categories or []}
        centrality_data: List[Dict[str, Any]] = []
        for cid, cat_name in category_name_by_id.items():
            row = agg_by_category.get(cid, {"code_degree": 0.0, "fragment_degree": 0.0})
            centrality_data.append(
                {
                    "category_id": cid,
                    "category_name": cat_name,
                    "code_degree": row["code_degree"],
                    "fragment_degree": row["fragment_degree"],
                }
            )
        centrality_data = sorted(
            centrality_data,
            key=lambda item: (
                -float(item.get("code_degree", 0.0)),
                -float(item.get("fragment_degree", 0.0)),
                str(item.get("category_name") or ""),
            ),
        )

        return {
            "project_id": str(project_id),
            "counts": counts,
            "category_centrality": centrality_data,
            "category_cooccurrence": [],
            "fallback": {"source": "sql", "reason": "neo4j_unavailable"},
        }

    async def _build_sql_evidence_fallback(
        self,
        *,
        project_id: UUID,
        db: AsyncSession,
        category_by_id: Dict[str, Category],
        critical_category_ids: List[str],
        target_max: int,
        min_interviews: int,
        max_share_per_interview: float,
    ) -> Dict[str, Any]:
        """
        Deterministic SQL fallback for semantic evidence when Qdrant is unavailable.
        Builds evidence from coded fragments scoped by project.
        """
        target_max = max(5, int(target_max))
        preferred_ids = [cid for cid in critical_category_ids if cid in category_by_id]
        if not preferred_ids:
            preferred_ids = list(category_by_id.keys())[:20]

        preferred_uuid_ids: List[UUID] = []
        for cid in preferred_ids:
            try:
                preferred_uuid_ids.append(UUID(str(cid)))
            except Exception:
                continue

        query = (
            select(
                Fragment.id.label("fragment_id"),
                Fragment.text.label("text"),
                Interview.id.label("interview_id"),
                Code.category_id.label("category_id"),
            )
            .select_from(code_fragment_links)
            .join(Code, code_fragment_links.c.code_id == Code.id)
            .join(Fragment, code_fragment_links.c.fragment_id == Fragment.id)
            .join(Interview, Fragment.interview_id == Interview.id)
            .where(
                Interview.project_id == project_id,
                Code.category_id.is_not(None),
            )
            .order_by(
                code_fragment_links.c.linked_at.desc(),
                Fragment.created_at.desc(),
            )
            .limit(max(target_max * 4, 120))
        )
        if preferred_uuid_ids:
            query = query.where(Code.category_id.in_(preferred_uuid_ids))

        rows = (await db.execute(query)).all()

        evidence_pool: List[Dict[str, Any]] = []
        fragment_to_interview: Dict[str, str] = {}
        for fragment_id, text, interview_id, category_id in rows:
            fid = str(fragment_id)
            iv = str(interview_id)
            cid = str(category_id) if category_id else None
            fragment_to_interview[fid] = iv
            evidence_pool.append(
                {
                    "id": fid,
                    "fragment_id": fid,
                    "text": str(text or ""),
                    "score": 0.5,
                    "codes": [],
                    "category_id": cid,
                }
            )

        sampled = self._sample_evidence_diverse(
            pool=evidence_pool,
            fragment_to_interview=fragment_to_interview,
            target_max=target_max,
            min_interviews=max(1, min_interviews),
            max_share_per_interview=max_share_per_interview,
        )

        evidence_index: List[Dict[str, Any]] = []
        evidence_by_category: Dict[str, List[Dict[str, Any]]] = {}
        for item in sampled:
            fid = str(item.get("fragment_id") or item.get("id") or "").strip()
            if not fid:
                continue
            cid = str(item.get("category_id") or "").strip() or None
            ev = {
                "id": fid,
                "fragment_id": fid,
                "interview_id": fragment_to_interview.get(fid),
                "category_id": cid,
                "edge_a_id": None,
                "edge_b_id": None,
                "text": str(item.get("text", ""))[:220],
                "score": item.get("score"),
                "codes": item.get("codes", []),
            }
            evidence_index.append(ev)
            if cid:
                evidence_by_category.setdefault(cid, []).append(
                    {
                        "id": fid,
                        "fragment_id": fid,
                        "text": str(item.get("text", "")),
                        "score": item.get("score"),
                        "codes": item.get("codes", []),
                    }
                )

        semantic_evidence: List[Dict[str, Any]] = []
        for cid in preferred_ids:
            frags = evidence_by_category.get(cid) or []
            if not frags:
                continue
            category = category_by_id.get(cid)
            semantic_evidence.append(
                {
                    "category_id": cid,
                    "category_name": category.name if category else cid,
                    "fragments": frags[:5],
                }
            )

        return {
            "semantic_evidence": semantic_evidence,
            "edge_evidence": [],
            "evidence_index": evidence_index,
            "evidence_pool": evidence_pool,
            "fragment_to_interview": fragment_to_interview,
            "evidence_by_category": evidence_by_category,
            "rows_count": len(rows),
        }

    async def _resolve_judge_rollout_policy(
        self,
        *,
        project_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Determines if Judge should run in warn-only vs strict for this project.
        Cohort-based progressive rollout:
        - Uses deterministic project bucket (0-99).
        - Requires recent quality stability before auto-switching to strict.
        """
        policy: Dict[str, Any] = {
            "enabled": bool(settings.THEORY_USE_JUDGE),
            "configured_warn_only": bool(settings.THEORY_JUDGE_WARN_ONLY),
            "effective_warn_only": bool(settings.THEORY_JUDGE_WARN_ONLY),
            "cohort_percent": int(settings.THEORY_JUDGE_STRICT_COHORT_PERCENT),
            "in_strict_cohort": False,
            "bucket": None,
            "window": int(settings.THEORY_JUDGE_STRICT_WINDOW),
            "min_theories": int(settings.THEORY_JUDGE_STRICT_MIN_THEORIES),
            "max_bad_runs": int(settings.THEORY_JUDGE_STRICT_MAX_BAD_RUNS),
            "promote_max_bad_runs": int(settings.THEORY_JUDGE_STRICT_PROMOTE_MAX_BAD_RUNS),
            "degrade_min_bad_runs": int(settings.THEORY_JUDGE_STRICT_DEGRADE_MIN_BAD_RUNS),
            "cooldown_runs": int(settings.THEORY_JUDGE_STRICT_COOLDOWN_RUNS),
            "max_mode_changes_per_window": int(settings.THEORY_JUDGE_STRICT_MAX_MODE_CHANGES_PER_WINDOW),
            "recent_theories": 0,
            "bad_runs": 0,
            "stable": False,
            "mode": "warn_only",
            "previous_mode": None,
            "mode_changed": False,
            "recent_mode_changes": 0,
            "runs_since_last_change": 0,
            "cooldown_active": False,
            "reason": "configured",
        }
        if not settings.THEORY_USE_JUDGE:
            return policy
        if not settings.THEORY_JUDGE_WARN_ONLY:
            policy["reason"] = "strict_configured"
            policy["effective_warn_only"] = False
            policy["mode"] = "strict"
            return policy

        cohort_percent = max(0, min(100, int(settings.THEORY_JUDGE_STRICT_COHORT_PERCENT)))
        if cohort_percent <= 0:
            policy["reason"] = "warn_only_no_cohort"
            return policy

        try:
            bucket = int(hashlib.sha1(str(project_id).encode("utf-8")).hexdigest()[:8], 16) % 100
        except Exception:
            bucket = 99
        in_cohort = bucket < cohort_percent
        policy["bucket"] = bucket
        policy["in_strict_cohort"] = in_cohort
        if not in_cohort:
            policy["reason"] = "warn_only_outside_cohort"
            return policy

        window = max(1, int(settings.THEORY_JUDGE_STRICT_WINDOW))
        min_theories = max(1, int(settings.THEORY_JUDGE_STRICT_MIN_THEORIES))
        max_bad_runs = max(0, int(settings.THEORY_JUDGE_STRICT_MAX_BAD_RUNS))
        promote_max_bad_runs = max(0, int(settings.THEORY_JUDGE_STRICT_PROMOTE_MAX_BAD_RUNS))
        degrade_min_bad_runs = max(0, int(settings.THEORY_JUDGE_STRICT_DEGRADE_MIN_BAD_RUNS))
        cooldown_runs = max(0, int(settings.THEORY_JUDGE_STRICT_COOLDOWN_RUNS))
        max_mode_changes_per_window = max(1, int(settings.THEORY_JUDGE_STRICT_MAX_MODE_CHANGES_PER_WINDOW))
        rows = await db.execute(
            select(Theory.validation)
            .where(Theory.project_id == project_id)
            .order_by(Theory.created_at.desc())
            .limit(max(window * 2, window + cooldown_runs + 2))
        )
        validations = rows.scalars().all()
        previous_mode_warn_only = bool(settings.THEORY_JUDGE_WARN_ONLY)
        previous_runs_since_last_change = cooldown_runs
        recent_mode_changes = 0
        if validations:
            latest_validation = validations[0] if isinstance(validations[0], dict) else {}
            previous_rollout = (latest_validation or {}).get("judge_rollout") if isinstance(latest_validation, dict) else {}
            if isinstance(previous_rollout, dict):
                previous_mode_warn_only = bool(
                    previous_rollout.get("effective_warn_only", previous_mode_warn_only)
                )
                prev_runs = previous_rollout.get("runs_since_last_change")
                if isinstance(prev_runs, int):
                    previous_runs_since_last_change = max(0, prev_runs)
        for validation in (validations or [])[:window]:
            if not isinstance(validation, dict):
                continue
            judge_rollout = validation.get("judge_rollout") or {}
            if isinstance(judge_rollout, dict) and bool(judge_rollout.get("mode_changed")):
                recent_mode_changes += 1
        recent = 0
        bad_runs = 0
        for validation in (validations or [])[:window]:
            if not isinstance(validation, dict):
                continue
            recent += 1
            claim_metrics = validation.get("claim_metrics") or {}
            quality_metrics = validation.get("quality_metrics") or {}
            judge_data = validation.get("judge") or {}
            interviews_covered = int(claim_metrics.get("interviews_covered") or 0)
            claims_without_evidence = int(claim_metrics.get("claims_without_evidence") or 0)
            evidence_index_size = int(quality_metrics.get("evidence_index_size") or 0)
            required_interviews = int(
                quality_metrics.get("judge_min_interviews_effective") or settings.THEORY_EVIDENCE_MIN_INTERVIEWS
            )
            warn_only_used = bool(judge_data.get("warn_only"))
            if (
                warn_only_used
                or claims_without_evidence > 0
                or interviews_covered < required_interviews
                or evidence_index_size < int(settings.THEORY_EVIDENCE_TARGET_MIN)
            ):
                bad_runs += 1

        stable = recent >= min_theories and bad_runs <= promote_max_bad_runs
        policy["recent_theories"] = recent
        policy["bad_runs"] = bad_runs
        policy["stable"] = stable
        policy["previous_mode"] = "warn_only" if previous_mode_warn_only else "strict"
        policy["recent_mode_changes"] = recent_mode_changes
        policy["runs_since_last_change"] = previous_runs_since_last_change

        candidate_warn_only = previous_mode_warn_only
        if recent >= min_theories and bad_runs <= promote_max_bad_runs:
            candidate_warn_only = False
        elif recent >= min_theories and bad_runs >= degrade_min_bad_runs:
            candidate_warn_only = True

        mode_changed = candidate_warn_only != previous_mode_warn_only
        if mode_changed and previous_runs_since_last_change < cooldown_runs:
            candidate_warn_only = previous_mode_warn_only
            mode_changed = False
            policy["cooldown_active"] = True
            policy["reason"] = "mode_change_cooldown"
        elif mode_changed and recent_mode_changes >= max_mode_changes_per_window:
            candidate_warn_only = previous_mode_warn_only
            mode_changed = False
            policy["reason"] = "mode_change_throttled"
        elif mode_changed and not candidate_warn_only:
            policy["reason"] = "strict_auto_promoted"
        elif mode_changed and candidate_warn_only:
            policy["reason"] = "strict_auto_degraded"
        else:
            if candidate_warn_only:
                policy["reason"] = "warn_only_insufficient_stability"
            else:
                policy["reason"] = "strict_auto_promoted"

        policy["effective_warn_only"] = bool(candidate_warn_only)
        policy["mode"] = "warn_only" if candidate_warn_only else "strict"
        policy["mode_changed"] = bool(mode_changed)
        policy["runs_since_last_change"] = 0 if mode_changed else (previous_runs_since_last_change + 1)
        policy["max_bad_runs"] = max_bad_runs
        return policy

    async def get_judge_rollout_policy(
        self,
        *,
        project_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        return await self._resolve_judge_rollout_policy(project_id=project_id, db=db)

    async def _sync_category_summary_vectors(
        self,
        *,
        project_id: UUID,
        owner_id: UUID,
        categories: List[Category],
        codes: List[Code],
    ) -> int:
        """
        Maintain category-level semantic units for coarse retrieval.
        """
        if not self.qdrant_service.enabled:
            return 0
        if not categories:
            return 0
        try:
            from qdrant_client.models import PointStruct
        except Exception:
            return 0

        code_labels_by_category: Dict[str, List[str]] = {}
        for code in codes or []:
            category_id = getattr(code, "category_id", None)
            label = (getattr(code, "label", None) or "").strip()
            if not category_id or not label:
                continue
            key = str(category_id)
            if key not in code_labels_by_category:
                code_labels_by_category[key] = []
            if label not in code_labels_by_category[key]:
                code_labels_by_category[key].append(label)

        summary_texts: List[str] = []
        summary_payloads: List[Dict[str, Any]] = []
        summary_ids: List[str] = []
        now_iso = datetime.utcnow().isoformat()
        for cat in categories:
            category_id = str(cat.id)
            code_labels = code_labels_by_category.get(category_id, [])[:10]
            code_part = f" Codigos asociados: {', '.join(code_labels)}." if code_labels else ""
            summary = redact_pii_text(f"{cat.name}. {cat.definition or ''}.{code_part}".strip())
            if not summary:
                continue
            summary_texts.append(summary)
            summary_ids.append(f"category_summary:{project_id}:{category_id}")
            summary_payloads.append(
                {
                    "text": summary,
                    "project_id": str(project_id),
                    "owner_id": str(owner_id),
                    "source_type": "category_summary",
                    "category_id": category_id,
                    "category_name": cat.name,
                    "created_at": now_iso,
                }
            )

        if not summary_texts:
            return 0

        vectors = await self.foundry_openai.generate_embeddings(summary_texts)
        if not vectors:
            return 0
        n = min(len(summary_ids), len(summary_payloads), len(vectors))
        points = [
            PointStruct(id=summary_ids[i], vector=vectors[i], payload=summary_payloads[i])
            for i in range(n)
        ]
        if not points:
            return 0
        await self.qdrant_service.upsert_vectors(project_id=project_id, points=points)
        return len(points)

    async def _sync_claim_vectors(
        self,
        *,
        project_id: UUID,
        owner_id: UUID,
        theory_id: UUID,
        paradigm: Dict[str, Any],
    ) -> int:
        """
        Persist claim semantic units for future coarse retrieval/contrast.
        """
        if not self.qdrant_service.enabled:
            return 0
        try:
            from qdrant_client.models import PointStruct
        except Exception:
            return 0

        section_to_type = {
            "conditions": "condition",
            "context": "condition",
            "intervening_conditions": "condition",
            "actions": "action",
            "consequences": "consequence",
            "propositions": "proposition",
        }
        texts: List[str] = []
        payloads: List[Dict[str, Any]] = []
        ids: List[str] = []
        now_iso = datetime.utcnow().isoformat()
        theory_uuid = uuid.UUID(str(theory_id))

        for section, claim_type in section_to_type.items():
            items = paradigm.get(section) or []
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or item.get("name") or "").strip()
                if not text:
                    continue
                text = redact_pii_text(text)
                evidence_ids = [
                    str(e).strip()
                    for e in (item.get("evidence_ids") or [])
                    if str(e).strip()
                ]
                claim_seed = f"{theory_id}:{section}:{idx}:{text}"
                claim_id = str(uuid.uuid5(theory_uuid, claim_seed))
                texts.append(text)
                ids.append(f"claim:{claim_id}")
                payloads.append(
                    {
                        "text": text,
                        "project_id": str(project_id),
                        "owner_id": str(owner_id),
                        "source_type": "claim",
                        "theory_id": str(theory_id),
                        "claim_id": claim_id,
                        "claim_type": claim_type,
                        "section": section,
                        "order": idx,
                        "evidence_ids": evidence_ids[:20],
                        "created_at": now_iso,
                    }
                )

        if not texts:
            return 0
        vectors = await self.foundry_openai.generate_embeddings(texts)
        if not vectors:
            return 0
        n = min(len(ids), len(payloads), len(vectors))
        points = [PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) for i in range(n)]
        if not points:
            return 0
        await self.qdrant_service.upsert_vectors(project_id=project_id, points=points)
        return len(points)

    async def _auto_code_if_needed(
        self,
        project_id: UUID,
        categories: List[Category],
        db: AsyncSession,
        mark_step: Callable[[str, int], Awaitable[None]],
        refresh_lock: Callable[[], Awaitable[None]],
        task_id: str,
    ) -> List[Category]:
        if len(categories) >= 2:
            return categories

        code_exists_result = await db.execute(
            select(Code.id).where(Code.project_id == project_id).limit(1)
        )
        if code_exists_result.first() is None:
            completed_interviews_result = await db.execute(
                select(Interview).where(
                    Interview.project_id == project_id,
                    Interview.transcription_status == "completed",
                    Interview.full_text.isnot(None),
                )
            )
            completed_interviews = completed_interviews_result.scalars().all()
            await mark_step("auto_code", 25)
            started = perf_counter()

            from ..database import get_session_local

            session_local = get_session_local()
            sem = asyncio.Semaphore(max(1, settings.THEORY_INTERVIEW_CONCURRENCY))

            async def _code_interview(iv_id: UUID):
                async with sem:
                    async with session_local() as iv_db:
                        # Ensure a single interview cannot stall the whole theory task forever.
                        await asyncio.wait_for(
                            self.coding_engine.auto_code_interview(project_id, iv_id, iv_db),
                            timeout=max(60, int(settings.THEORY_AUTOCODE_INTERVIEW_TIMEOUT_SECONDS)),
                        )

            if completed_interviews:
                n_total = len(completed_interviews)
                n_done = 0
                failures: list[str] = []
                heartbeat_seconds = 8
                timeout_per_interview = max(
                    60,
                    int(settings.THEORY_AUTOCODE_INTERVIEW_TIMEOUT_SECONDS),
                )

                pending: set[asyncio.Task[None]] = {
                    asyncio.create_task(_code_interview(iv.id)) for iv in completed_interviews
                }
                while pending:
                    done, pending = await asyncio.wait(
                        pending,
                        timeout=heartbeat_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if done:
                        for fut in done:
                            try:
                                await fut
                            except Exception as e:
                                failures.append(str(e)[:300])
                            finally:
                                n_done += 1
                        # Keep UI moving inside the long auto-code stage (25% -> 40%).
                        stage_pct = 25 + int((15 * n_done) / max(1, n_total))
                        await mark_step("auto_code", stage_pct)
                        await refresh_lock()
                        continue

                    # Heartbeat for long-running interviews so UI doesn't look frozen at 25%.
                    elapsed = perf_counter() - started
                    heartbeat_cap = 39
                    heartbeat_window = heartbeat_cap - 25
                    expected_window_seconds = max(120.0, float(timeout_per_interview))
                    heartbeat_pct = 25 + min(
                        heartbeat_window,
                        int((heartbeat_window * elapsed) / expected_window_seconds),
                    )
                    await mark_step("auto_code", max(25, min(heartbeat_cap, heartbeat_pct)))
                    await refresh_lock()

                if failures:
                    # Best-effort: auto-coding can partially succeed; pipeline will still
                    # enforce minimum categories later.
                    logger.warning(
                        "[theory][%s] auto_code had %d/%d interview failures (showing up to 3): %s",
                        task_id,
                        len(failures),
                        n_total,
                        failures[:3],
                    )
            else:
                # No interviews to auto-code; keep pipeline moving.
                await refresh_lock()

            logger.info(
                "[theory][%s] auto_code interviews=%d elapsed=%.2fs",
                task_id,
                len(completed_interviews),
                perf_counter() - started,
            )
            self._log_stage(
                task_id,
                project_id,
                "auto_code_interviews",
                started,
                interviews=len(completed_interviews),
            )

        code_result = await db.execute(select(Code).filter(Code.project_id == project_id))
        codes_for_bootstrap = code_result.scalars().all()
        if len(codes_for_bootstrap) >= 2:
            bootstrap_started = perf_counter()
            category_by_label = {c.name.strip().lower(): c for c in categories if c.name}
            for code in codes_for_bootstrap:
                if code.category_id:
                    continue
                label = (code.label or "").strip()
                if not label:
                    continue
                key = label.lower()
                category = category_by_label.get(key)
                if not category:
                    category = Category(
                        project_id=project_id,
                        name=label[:500],
                        definition="Auto-generada desde codigos durante teorizacion",
                        created_at=datetime.utcnow(),
                    )
                    db.add(category)
                    await db.flush()
                    category_by_label[key] = category
                code.category_id = category.id
            await db.commit()
            categories = (
                await db.execute(select(Category).filter(Category.project_id == project_id))
            ).scalars().all()
            self._log_stage(
                task_id,
                project_id,
                "bootstrap_categories_from_codes",
                bootstrap_started,
                categories=len(categories),
                codes=len(codes_for_bootstrap),
            )

        return categories

    async def run(
        self,
        task_id: str,
        project_id: UUID,
        user_uuid: UUID,
        request: TheoryGenerateRequest,
        db: AsyncSession,
        mark_step: Callable[[str, int], Awaitable[None]],
        refresh_lock: Callable[[], Awaitable[None]],
    ) -> Dict[str, Any]:
        request_payload = request.model_dump(exclude_none=True)
        category_summary_vectors_synced = 0
        category_summary_sync_ms = 0.0
        coarse_summary_hits = 0
        refined_category_count = 0
        judge_rollout_policy: Dict[str, Any] = {
            "enabled": bool(settings.THEORY_USE_JUDGE),
            "configured_warn_only": bool(settings.THEORY_JUDGE_WARN_ONLY),
            "effective_warn_only": bool(settings.THEORY_JUDGE_WARN_ONLY),
            "reason": "configured",
        }
        deterministic_routing = self._build_deterministic_routing_plan(
            use_subgraph_evidence=bool(settings.THEORY_USE_SUBGRAPH_EVIDENCE),
            use_model_router=bool(request.use_model_router),
            qdrant_enabled=bool(self.qdrant_service.enabled),
            neo4j_enabled=bool(self.neo4j_service.enabled),
        )
        network_metrics_source = "neo4j"
        semantic_evidence_source = (
            "qdrant_subgraph" if settings.THEORY_USE_SUBGRAPH_EVIDENCE else "qdrant_basic"
        )

        await mark_step("load_project", 5)
        stage_started = perf_counter()
        project = (
            await db.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.owner_id == user_uuid,
                )
            )
        ).scalar_one_or_none()
        if not project:
            raise TheoryPipelineError("NOT_FOUND", "Project not found")
        self._log_stage(
            task_id,
            project_id,
            "load_project",
            stage_started,
            owner_id=str(user_uuid),
        )

        if settings.THEORY_USE_JUDGE:
            stage_started = perf_counter()
            judge_rollout_policy = await self._resolve_judge_rollout_policy(
                project_id=project_id,
                db=db,
            )
            self._log_stage(
                task_id,
                project_id,
                "judge_rollout_policy",
                stage_started,
                policy=judge_rollout_policy,
            )

        await mark_step("load_categories", 10)
        stage_started = perf_counter()
        categories = (
            await db.execute(select(Category).filter(Category.project_id == project_id))
        ).scalars().all()
        self._log_stage(
            task_id,
            project_id,
            "load_categories",
            stage_started,
            categories=len(categories),
        )

        stage_started = perf_counter()
        categories = await self._auto_code_if_needed(
            project_id=project_id,
            categories=categories,
            db=db,
            mark_step=mark_step,
            refresh_lock=refresh_lock,
            task_id=task_id,
        )
        self._log_stage(
            task_id,
            project_id,
            "ensure_categories_with_autocode",
            stage_started,
            categories=len(categories),
        )

        if len(categories) < 2:
            interviews_total = (
                await db.execute(
                    select(func.count()).select_from(Interview).where(Interview.project_id == project_id)
                )
            ).scalar() or 0
            interviews_completed = (
                await db.execute(
                    select(func.count())
                    .select_from(Interview)
                    .where(
                        Interview.project_id == project_id,
                        Interview.transcription_status == "completed",
                    )
                )
            ).scalar() or 0
            codes_total = (
                await db.execute(select(func.count()).select_from(Code).where(Code.project_id == project_id))
            ).scalar() or 0
            raise TheoryPipelineError(
                "INSUFFICIENT_CATEGORIES",
                (
                    "No hay suficientes categorias para teorizacion (minimo 2). "
                    f"Estado actual: entrevistas={interviews_total}, "
                    f"entrevistas_completadas={interviews_completed}, "
                    f"codigos={codes_total}, categorias={len(categories)}."
                ),
            )

        await mark_step("neo4j_taxonomy_sync", 45)
        stage_started = perf_counter()
        codes = (
            await db.execute(select(Code).filter(Code.project_id == project_id))
        ).scalars().all()
        neo4j_taxonomy_sync_ok = True
        try:
            await self.neo4j_service.ensure_project_node(project_id, project.name)
            await self.neo4j_service.batch_sync_taxonomy(
                project_id=project_id,
                categories=[(cat.id, cat.name) for cat in categories],
                code_category_pairs=[(code.id, code.category_id) for code in codes if code.category_id],
            )
        except Exception as e:
            neo4j_taxonomy_sync_ok = False
            if settings.THEORY_USE_DETERMINISTIC_ROUTING:
                logger.warning(
                    "[theory][%s] neo4j taxonomy sync degraded to SQL routing: %s",
                    task_id,
                    str(e)[:300],
                )
            else:
                raise
        self._log_stage(
            task_id,
            project_id,
            "neo4j_taxonomy_sync",
            stage_started,
            categories=len(categories),
            codes=len(codes),
            success=neo4j_taxonomy_sync_ok,
        )

        if settings.THEORY_USE_SUBGRAPH_EVIDENCE:
            summary_sync_started = perf_counter()
            try:
                category_summary_vectors_synced = await asyncio.wait_for(
                    self._sync_category_summary_vectors(
                        project_id=project_id,
                        owner_id=user_uuid,
                        categories=categories,
                        codes=codes,
                    ),
                    timeout=max(10, int(settings.CODING_QDRANT_UPSERT_TIMEOUT_SECONDS)),
                )
            except Exception as e:
                logger.warning(
                    "[theory][%s] qdrant category summary sync skipped: %s",
                    task_id,
                    str(e)[:300],
                )
                category_summary_vectors_synced = 0
            category_summary_sync_ms = round((perf_counter() - summary_sync_started) * 1000.0, 2)
            self._log_stage(
                task_id,
                project_id,
                "qdrant_category_summary_sync",
                summary_sync_started,
                vectors_synced=category_summary_vectors_synced,
            )

        await mark_step("network_metrics", 60)
        stage_started = perf_counter()
        network_metrics_fallback_reason = None
        try:
            network_metrics = await self.neo4j_service.get_project_network_metrics(project_id)
            network_metrics_source = "neo4j"
        except Exception as e:
            if not settings.THEORY_USE_DETERMINISTIC_ROUTING:
                raise
            network_metrics = await self._build_sql_network_metrics_fallback(
                project_id=project_id,
                db=db,
                categories=categories,
                codes=codes,
            )
            network_metrics_source = "sql_fallback"
            network_metrics_fallback_reason = str(e)[:300]
        network_metrics_elapsed_ms = round((perf_counter() - stage_started) * 1000.0, 2)
        self._log_stage(
            task_id,
            project_id,
            "network_metrics",
            stage_started,
            source=network_metrics_source,
            fallback_reason=network_metrics_fallback_reason,
            counts=network_metrics.get("counts", {}),
            centrality=len(network_metrics.get("category_centrality", [])),
            cooccurrence=len(network_metrics.get("category_cooccurrence", [])),
        )

        await mark_step("semantic_evidence", 70)
        stage_started = perf_counter()
        category_by_id: dict[str, Category] = {str(c.id): c for c in categories}
        semantic_evidence: list[dict] = []
        edge_evidence: list[dict] = []
        evidence_index: list[dict] = []
        evidence_pool: list[dict] = []
        fragment_to_interview: dict[str, str] = {}
        evidence_by_category: dict[str, list[dict]] = {}
        critical_category_ids: list[str] = []
        critical_edges: list[tuple[str, str]] = []
        semantic_evidence_fallback_reason = None

        if settings.THEORY_USE_SUBGRAPH_EVIDENCE:
            critical_category_ids, critical_edges = self._select_critical_subgraph(
                network_metrics=network_metrics,
                top_centrality=settings.THEORY_MAX_CRITICAL_CATEGORIES,
                top_edges=settings.THEORY_MAX_CRITICAL_EDGES,
                top_bridges=settings.THEORY_MAX_BRIDGE_CATEGORIES,
            )
            refined_category_ids = list(critical_category_ids)

            if refined_category_ids:
                coarse_specs: list[dict] = []
                for cid in refined_category_ids:
                    cat = category_by_id.get(cid)
                    if not cat:
                        continue
                    coarse_specs.append(
                        {
                            "category_id": cid,
                            "text": f"{cat.name}. {cat.definition or ''}".strip(),
                        }
                    )
                coarse_query_texts = [q.get("text") for q in coarse_specs if q.get("text")]
                coarse_embeddings = (
                    await self.foundry_openai.generate_embeddings(coarse_query_texts)
                    if coarse_query_texts
                    else []
                )
                n_coarse = min(len(coarse_specs), len(coarse_embeddings))
                coarse_specs = coarse_specs[:n_coarse]
                coarse_embeddings = coarse_embeddings[:n_coarse]
                sem_coarse = asyncio.Semaphore(max(1, int(settings.THEORY_QDRANT_RETRIEVAL_CONCURRENCY)))

                async def _fetch_summary(spec: dict, vec: list[float]):
                    async with sem_coarse:
                        hits = await self.qdrant_service.search_supporting_fragments(
                            project_id=project_id,
                            query_vector=vec,
                            limit=2,
                            owner_id=str(user_uuid),
                            source_types=["category_summary"],
                            allow_legacy_fallback=False,
                        )
                        return spec, hits

                coarse_results = await asyncio.gather(
                    *[_fetch_summary(spec, vec) for spec, vec in zip(coarse_specs, coarse_embeddings)],
                    return_exceptions=False,
                )
                coarse_summary_hits = sum(len(hits or []) for _spec, hits in coarse_results)
                discovered: list[str] = []
                for _spec, hits in coarse_results:
                    for hit in hits or []:
                        if not isinstance(hit, dict):
                            continue
                        metadata = hit.get("metadata") or {}
                        cat_id = str(metadata.get("category_id") or hit.get("category_id") or "").strip()
                        if cat_id and cat_id in category_by_id:
                            discovered.append(cat_id)
                for cid in discovered:
                    if cid not in refined_category_ids:
                        refined_category_ids.append(cid)
                max_refined = max(
                    int(settings.THEORY_MAX_CRITICAL_CATEGORIES),
                    int(settings.THEORY_MAX_CRITICAL_CATEGORIES) * 2,
                )
                refined_category_ids = refined_category_ids[:max_refined]

            refined_category_count = len(refined_category_ids)

            query_specs: list[dict] = []
            for cid in refined_category_ids:
                cat = category_by_id.get(cid)
                if not cat:
                    continue
                query_specs.append(
                    {
                        "kind": "category",
                        "category_id": cid,
                        "text": f"{cat.name}. {cat.definition or ''}".strip(),
                        "limit": 5,
                    }
                )
            for a, b in critical_edges:
                ca = category_by_id.get(a)
                cb = category_by_id.get(b)
                if not ca or not cb:
                    continue
                query_specs.append(
                    {
                        "kind": "edge",
                        "edge_a_id": a,
                        "edge_b_id": b,
                        "text": f"{ca.name} + {cb.name}. ¿Como se conectan en la experiencia? Evidencia concreta.",
                        "limit": 3,
                    }
                )

            if settings.THEORY_MAX_QDRANT_QUERIES > 0:
                query_specs = query_specs[: int(settings.THEORY_MAX_QDRANT_QUERIES)]

            query_texts = [q["text"] for q in query_specs if q.get("text")]
            embeddings = await self.foundry_openai.generate_embeddings(query_texts) if query_texts else []
            n = min(len(query_specs), len(embeddings))
            query_specs = query_specs[:n]
            embeddings = embeddings[:n]

            sem_q = asyncio.Semaphore(max(1, int(settings.THEORY_QDRANT_RETRIEVAL_CONCURRENCY)))

            async def _qdrant_fetch(spec: dict, vec: list[float]):
                async with sem_q:
                    frags = await self.qdrant_service.search_supporting_fragments(
                        project_id=project_id,
                        query_vector=vec,
                        limit=int(spec.get("limit") or 3),
                        owner_id=str(user_uuid),
                        source_types=["fragment"],
                    )
                    return spec, frags

            fetched = await asyncio.gather(
                *[_qdrant_fetch(spec, vec) for spec, vec in zip(query_specs, embeddings)],
                return_exceptions=False,
            )

            for spec, frags in fetched:
                kind = spec.get("kind")
                if kind == "category":
                    cid = str(spec.get("category_id"))
                    cat = category_by_id.get(cid)
                    semantic_evidence.append(
                        {
                            "category_id": cid,
                            "category_name": cat.name if cat else cid,
                            "fragments": frags,
                        }
                    )
                    evidence_by_category[cid] = frags
                    for f in frags or []:
                        if isinstance(f, dict):
                            evidence_pool.append({**f, "category_id": cid})
                elif kind == "edge":
                    a = str(spec.get("edge_a_id"))
                    b = str(spec.get("edge_b_id"))
                    ca = category_by_id.get(a)
                    cb = category_by_id.get(b)
                    edge_evidence.append(
                        {
                            "edge_a_id": a,
                            "edge_a_name": ca.name if ca else a,
                            "edge_b_id": b,
                            "edge_b_name": cb.name if cb else b,
                            "fragments": frags,
                        }
                    )
                    for f in frags or []:
                        if isinstance(f, dict):
                            evidence_pool.append({**f, "edge_a_id": a, "edge_b_id": b})

            candidate_ids = list(
                {
                    str(p.get("fragment_id") or p.get("id") or "").strip()
                    for p in evidence_pool
                    if isinstance(p, dict)
                }
            )
            candidate_ids = [c for c in candidate_ids if c]
            if candidate_ids:
                rows = await db.execute(
                    select(Fragment.id, Interview.id)
                    .join(Interview, Fragment.interview_id == Interview.id)
                    .where(
                        Fragment.id.in_(candidate_ids[:2000]),
                        Interview.project_id == project_id,
                    )
                )
                fragment_to_interview = {str(fid): str(iv) for fid, iv in rows.all()}

            sampled = self._sample_evidence_diverse(
                pool=evidence_pool,
                fragment_to_interview=fragment_to_interview,
                target_max=settings.THEORY_EVIDENCE_TARGET_MAX,
                min_interviews=min(
                    settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                    len(set(fragment_to_interview.values())) or settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                ),
                max_share_per_interview=settings.THEORY_EVIDENCE_MAX_SHARE_PER_INTERVIEW,
            )

            evidence_index = []
            for item in sampled:
                fid = str(item.get("fragment_id") or item.get("id") or "").strip()
                if not fid:
                    continue
                evidence_index.append(
                    {
                        "id": fid,
                        "fragment_id": fid,
                        "interview_id": fragment_to_interview.get(fid),
                        "category_id": item.get("category_id"),
                        "edge_a_id": item.get("edge_a_id"),
                        "edge_b_id": item.get("edge_b_id"),
                        "text": str(item.get("text", ""))[:220],
                        "score": item.get("score"),
                        "codes": item.get("codes", []),
                    }
                )
        else:
            top_categories = [
                (item.get("category_id"), category_by_id.get(item.get("category_id")))
                for item in network_metrics.get("category_centrality", [])[:3]
                if category_by_id.get(item.get("category_id"))
            ]

            async def _fetch_evidence(category_id: str, category_obj: Category):
                query_text = f"{category_obj.name}. {category_obj.definition or ''}".strip()
                embeddings = await self.foundry_openai.generate_embeddings([query_text])
                if not embeddings:
                    return None
                fragments = await self.qdrant_service.search_supporting_fragments(
                    project_id=project_id,
                    query_vector=embeddings[0],
                    limit=3,
                    owner_id=str(user_uuid),
                )
                return {
                    "category_id": category_id,
                    "category_name": category_obj.name,
                    "fragments": fragments,
                }

            evidence_results = await asyncio.gather(
                *[_fetch_evidence(cid, cobj) for cid, cobj in top_categories],
                return_exceptions=False,
            )
            semantic_evidence = [r for r in evidence_results if r is not None]
            evidence_by_category = {item["category_id"]: item["fragments"] for item in semantic_evidence}
            for item in semantic_evidence:
                cid = str(item.get("category_id") or "")
                for frag in item.get("fragments") or []:
                    if isinstance(frag, dict):
                        evidence_pool.append({**frag, "category_id": cid})

        if evidence_index:
            semantic_evidence_source = (
                "qdrant_subgraph" if settings.THEORY_USE_SUBGRAPH_EVIDENCE else "qdrant_basic"
            )

        if settings.THEORY_USE_DETERMINISTIC_ROUTING and not evidence_index:
            fallback = await self._build_sql_evidence_fallback(
                project_id=project_id,
                db=db,
                category_by_id=category_by_id,
                critical_category_ids=(
                    critical_category_ids
                    or [
                        str(item.get("category_id"))
                        for item in (network_metrics.get("category_centrality") or [])[:20]
                        if item.get("category_id")
                    ]
                ),
                target_max=settings.THEORY_EVIDENCE_TARGET_MAX,
                min_interviews=settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                max_share_per_interview=settings.THEORY_EVIDENCE_MAX_SHARE_PER_INTERVIEW,
            )
            if fallback.get("evidence_index"):
                semantic_evidence = fallback.get("semantic_evidence") or []
                edge_evidence = fallback.get("edge_evidence") or []
                evidence_index = fallback.get("evidence_index") or []
                evidence_pool = fallback.get("evidence_pool") or []
                fragment_to_interview = fallback.get("fragment_to_interview") or {}
                evidence_by_category = fallback.get("evidence_by_category") or {}
                semantic_evidence_source = "sql_fallback"
                semantic_evidence_fallback_reason = "qdrant_empty_or_unavailable"

        qdrant_retrieval_ms = round((perf_counter() - stage_started) * 1000.0, 2)

        self._log_stage(
            task_id,
            project_id,
            "semantic_evidence",
            stage_started,
            source=semantic_evidence_source,
            fallback_reason=semantic_evidence_fallback_reason,
            categories_with_evidence=len(semantic_evidence),
            edge_evidence=len(edge_evidence),
            coarse_summary_hits=coarse_summary_hits,
            refined_category_count=refined_category_count,
            total_fragments=sum(len(item.get("fragments", [])) for item in semantic_evidence)
            + sum(len(item.get("fragments", [])) for item in edge_evidence),
            evidence_index_size=len(evidence_index),
            evidence_interviews=len({e.get("interview_id") for e in evidence_index if e.get("interview_id")}),
        )

        cats_data = [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.definition or "",
                "semantic_evidence": evidence_by_category.get(str(c.id), []),
            }
            for c in categories
        ]

        identify_model = settings.MODEL_REASONING_ADVANCED
        paradigm_model = settings.MODEL_ROUTER
        gaps_model = settings.MODEL_REASONING_FAST
        identify_context_limit = self._resolve_context_limit(identify_model)
        paradigm_context_limit = self._resolve_context_limit(paradigm_model)
        gaps_context_limit = self._resolve_context_limit(gaps_model)
        template_key = (getattr(project, "domain_template", "generic") or "generic").strip().lower()

        state = StrategyState(
            max_cats=min(settings.THEORY_MAX_CATS_FOR_LLM, settings.THEORY_BUDGET_FALLBACK_MAX_CATS),
            max_frags_per_cat=min(
                settings.THEORY_MAX_EVIDENCE_FRAGS,
                settings.THEORY_BUDGET_FALLBACK_MAX_FRAGS_PER_CAT,
            ),
            max_frag_chars=min(settings.THEORY_MAX_FRAG_CHARS, settings.THEORY_BUDGET_FALLBACK_MAX_FRAG_CHARS),
            max_network_top=min(settings.THEORY_MAX_NETWORK_TOP, settings.THEORY_BUDGET_FALLBACK_MAX_NETWORK_TOP),
        )

        await mark_step("identify_central_category", 80)
        stage_started = perf_counter()

        def _identify_messages_builder() -> List[Dict[str, Any]]:
            cats_payload = self._slim_cats_for_llm(cats_data, network_metrics, state)
            network_payload = self._slim_network_for_llm(network_metrics, state)
            return self.theory_engine.build_identify_messages(
                categories=cats_payload,
                network=network_payload,
                template_key=template_key,
            )

        _, identify_budget = ensure_within_budget(
            messages_builder=_identify_messages_builder,
            model=identify_model,
            context_limit=identify_context_limit,
            max_output_tokens=settings.THEORY_LLM_MAX_OUTPUT_TOKENS_LARGE,
            degrade_cb=state.degrade,
            margin_tokens=settings.THEORY_BUDGET_MARGIN_TOKENS,
            max_degradation_steps=settings.THEORY_BUDGET_MAX_DEGRADATION_STEPS,
        )
        logger.info(
            "[theory][%s] budget identify fits=%s input_tokens=%s steps=%s",
            task_id,
            identify_budget.get("fits"),
            identify_budget.get("input_tokens_estimate"),
            identify_budget.get("degradation_steps", []),
        )
        cats_identify = self._slim_cats_for_llm(cats_data, network_metrics, state)
        network_identify = self._slim_network_for_llm(network_metrics, state)

        central_cat_data = await self.theory_engine.identify_central_category(
            cats_identify,
            network_identify,
            template_key=template_key,
        )
        identify_llm_ms = round((perf_counter() - stage_started) * 1000.0, 2)
        self._log_stage(
            task_id,
            project_id,
            "identify_central_category",
            stage_started,
            prompt_version=settings.THEORY_PROMPT_VERSION,
            template_key=template_key,
            input_tokens_estimate=identify_budget.get("input_tokens_estimate"),
            degradation_steps=identify_budget.get("degradation_steps", []),
            selected=central_cat_data.get("selected_central_category"),
        )

        await mark_step("build_straussian_paradigm", 87)
        stage_started = perf_counter()

        def _step2_cats_payload() -> List[Dict[str, Any]]:
            base = self._slim_cats_for_llm(cats_data, network_metrics, state)
            if state.remove_evidence_step2:
                return self._cats_no_evidence(base)
            return base

        def _paradigm_messages_builder() -> List[Dict[str, Any]]:
            return self.theory_engine.build_paradigm_messages(
                central_cat=central_cat_data["selected_central_category"],
                other_cats=_step2_cats_payload(),
                template_key=template_key,
            )

        _, paradigm_budget = ensure_within_budget(
            messages_builder=_paradigm_messages_builder,
            model=paradigm_model,
            context_limit=paradigm_context_limit,
            max_output_tokens=settings.THEORY_LLM_MAX_OUTPUT_TOKENS,
            degrade_cb=state.degrade,
            margin_tokens=settings.THEORY_BUDGET_MARGIN_TOKENS,
            max_degradation_steps=settings.THEORY_BUDGET_MAX_DEGRADATION_STEPS,
        )
        logger.info(
            "[theory][%s] budget paradigm fits=%s input_tokens=%s steps=%s",
            task_id,
            paradigm_budget.get("fits"),
            paradigm_budget.get("input_tokens_estimate"),
            paradigm_budget.get("degradation_steps", []),
        )
        paradigm = await self.theory_engine.build_straussian_paradigm(
            central_cat_data["selected_central_category"],
            _step2_cats_payload(),
            template_key=template_key,
            use_model_router=bool(request.use_model_router),
        )
        paradigm = self.theory_engine.normalize_paradigm(
            paradigm,
            central_cat=central_cat_data["selected_central_category"],
        )

        # Backward-compatible fallback: ensure evidence_index is present for repairs/judge.
        if not evidence_index:
            evidence_index = []
            for cat in cats_data:
                for frag in (cat.get("semantic_evidence") or [])[:1]:
                    if not isinstance(frag, dict):
                        continue
                    fid = frag.get("fragment_id") or frag.get("id")
                    if not fid:
                        continue
                    evidence_index.append(
                        {
                            "id": str(fid),
                            "fragment_id": str(fid),
                            "category_id": cat.get("id"),
                            "category_name": cat.get("name"),
                            "text": str(frag.get("text", ""))[:220],
                            "score": frag.get("score"),
                        }
                    )

        paradigm_validation_before = self.theory_engine.validate_paradigm(paradigm)
        repairs_applied: List[str] = []
        repair_attempts = 0
        available_category_names = [
            str(c.get("name")) for c in (cats_data or []) if isinstance(c, dict) and c.get("name")
        ]
        if not paradigm_validation_before.get("consequences_ok"):
            try:
                repair_attempts += 1
                repaired_consequences = await self.theory_engine.repair_consequences(
                    central_cat=central_cat_data["selected_central_category"],
                    paradigm=paradigm,
                    evidence_index=evidence_index,
                )
                if repaired_consequences:
                    paradigm["consequences"] = repaired_consequences
                    repairs_applied.append("consequences")
            except Exception:
                # Best-effort repair only; keep original output if repair fails.
                pass

        if not paradigm_validation_before.get("propositions_ok"):
            try:
                repair_attempts += 1
                repaired_props = await self.theory_engine.repair_propositions(
                    central_cat=central_cat_data["selected_central_category"],
                    paradigm=paradigm,
                    evidence_index=evidence_index,
                    target_count=7,
                )
                if repaired_props:
                    paradigm["propositions"] = repaired_props
                    repairs_applied.append("propositions")
            except Exception:
                pass

        # Ensure constructs introduced by propositions are reflected as categories in context/intervening_conditions.
        try:
            ctx = paradigm.get("context") or []
            ic = paradigm.get("intervening_conditions") or []
            needs_ctx_repair = (not isinstance(ctx, list) or len(ctx) == 0) and (not isinstance(ic, list) or len(ic) == 0)
            if needs_ctx_repair:
                repair_attempts += 1
                repaired_ctx = await self.theory_engine.repair_context_intervening(
                    central_cat=central_cat_data["selected_central_category"],
                    paradigm=paradigm,
                    evidence_index=evidence_index,
                    available_categories=available_category_names,
                    target_min_each=2,
                )
                if repaired_ctx.get("context") or repaired_ctx.get("intervening_conditions"):
                    # Merge (dedupe by name string) without clobbering existing values if present.
                    def _norm_name(v: Any) -> str:
                        if isinstance(v, dict):
                            return str(v.get("name") or v.get("text") or "").strip().lower()
                        return str(v or "").strip().lower()

                    existing_ctx = paradigm.get("context") if isinstance(paradigm.get("context"), list) else []
                    existing_ic = paradigm.get("intervening_conditions") if isinstance(paradigm.get("intervening_conditions"), list) else []
                    ctx_names = {_norm_name(v) for v in existing_ctx if _norm_name(v)}
                    ic_names = {_norm_name(v) for v in existing_ic if _norm_name(v)}

                    for item in repaired_ctx.get("context", []) or []:
                        n = _norm_name(item)
                        if n and n not in ctx_names:
                            existing_ctx.append(item)
                            ctx_names.add(n)
                    for item in repaired_ctx.get("intervening_conditions", []) or []:
                        n = _norm_name(item)
                        if n and n not in ic_names:
                            existing_ic.append(item)
                            ic_names.add(n)

                    paradigm["context"] = existing_ctx
                    paradigm["intervening_conditions"] = existing_ic
                    repairs_applied.append("context_intervening")
        except Exception:
            pass

        judge_result: Dict[str, Any] = {"enabled": False}
        judge_fail_reason = ""
        judge_available_interviews = 0
        effective_judge_warn_only = bool(judge_rollout_policy.get("effective_warn_only", settings.THEORY_JUDGE_WARN_ONLY))
        if settings.THEORY_USE_JUDGE:
            completed_interviews = (
                await db.execute(
                    select(func.count(func.distinct(Interview.id)))
                    .where(
                        Interview.project_id == project_id,
                        Interview.transcription_status == "completed",
                    )
                )
            ).scalar() or 0
            total_interviews = (
                await db.execute(
                    select(func.count(func.distinct(Interview.id)))
                    .where(Interview.project_id == project_id)
                )
            ).scalar() or 0
            judge_available_interviews = int(completed_interviews or total_interviews or 0)
            judge = TheoryJudge(
                min_interviews=settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                max_share_per_interview=settings.THEORY_EVIDENCE_MAX_SHARE_PER_INTERVIEW,
                adaptive_thresholds=bool(settings.THEORY_JUDGE_ADAPTIVE_THRESHOLDS),
                available_interviews=judge_available_interviews,
                min_interviews_floor=int(settings.THEORY_JUDGE_MIN_INTERVIEWS_FLOOR),
                min_interviews_ratio=float(settings.THEORY_JUDGE_MIN_INTERVIEWS_RATIO),
                balance_min_evidence=int(settings.THEORY_JUDGE_BALANCE_MIN_EVIDENCE),
            )
            for _attempt in range(2):
                paradigm_evidence_ids = self._extract_evidence_ids(paradigm)
                fragment_to_interview_paradigm: dict[str, str] = {}
                missing_evidence_ids: list[str] = []
                if paradigm_evidence_ids:
                    rows = await db.execute(
                        select(Fragment.id, Interview.id)
                        .join(Interview, Fragment.interview_id == Interview.id)
                        .where(
                            Fragment.id.in_(paradigm_evidence_ids[:2000]),
                            Interview.project_id == project_id,
                        )
                    )
                    fragment_to_interview_paradigm = {str(fid): str(iv) for fid, iv in rows.all()}
                    missing_evidence_ids = [fid for fid in paradigm_evidence_ids if fid not in fragment_to_interview_paradigm]

                judge_result = judge.evaluate(
                    paradigm=paradigm,
                    fragment_to_interview=fragment_to_interview_paradigm,
                    missing_evidence_ids=missing_evidence_ids,
                    known_category_names=available_category_names,
                )
                if judge_result.get("ok"):
                    break

                errors = judge_result.get("errors") or []
                error_codes = {str(e.get("code")) for e in errors if e.get("code")}

                # Real re-sampling when coverage fails.
                if "COVERAGE_MIN_INTERVIEWS" in error_codes and evidence_pool and fragment_to_interview:
                    sampled = self._sample_evidence_diverse(
                        pool=evidence_pool,
                        fragment_to_interview=fragment_to_interview,
                        target_max=settings.THEORY_EVIDENCE_TARGET_MAX,
                        min_interviews=min(
                            settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                            len(set(fragment_to_interview.values())) or settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                        ),
                        max_share_per_interview=max(0.2, settings.THEORY_EVIDENCE_MAX_SHARE_PER_INTERVIEW - 0.1),
                    )
                    refreshed_index: list[dict] = []
                    for item in sampled:
                        fid = str(item.get("fragment_id") or item.get("id") or "").strip()
                        if not fid:
                            continue
                        refreshed_index.append(
                            {
                                "id": fid,
                                "fragment_id": fid,
                                "interview_id": fragment_to_interview.get(fid),
                                "category_id": item.get("category_id"),
                                "edge_a_id": item.get("edge_a_id"),
                                "edge_b_id": item.get("edge_b_id"),
                                "text": str(item.get("text", ""))[:220],
                                "score": item.get("score"),
                                "codes": item.get("codes", []),
                            }
                        )
                    if refreshed_index:
                        evidence_index = refreshed_index

                # Directed retrieval fallback for material balance issues.
                if "BALANCE_CONSEQUENCES" in error_codes:
                    try:
                        material_hits = await self._augment_material_evidence(
                            project_id=project_id,
                            owner_id=user_uuid,
                            limit_per_query=settings.THEORY_MATERIAL_QUERY_LIMIT,
                        )
                    except Exception:
                        material_hits = []
                    if material_hits:
                        for hit in material_hits:
                            evidence_pool.append({**hit, "category_id": None})
                        new_ids = list(
                            {
                                str(h.get("fragment_id") or h.get("id") or "").strip()
                                for h in material_hits
                                if isinstance(h, dict)
                            }
                        )
                        new_ids = [x for x in new_ids if x]
                        if new_ids:
                            rows = await db.execute(
                                select(Fragment.id, Interview.id)
                                .join(Interview, Fragment.interview_id == Interview.id)
                                .where(
                                    Fragment.id.in_(new_ids[:2000]),
                                    Interview.project_id == project_id,
                                )
                            )
                            for fid, iv in rows.all():
                                fragment_to_interview[str(fid)] = str(iv)
                        for item in material_hits:
                            fid = str(item.get("fragment_id") or item.get("id") or "").strip()
                            if not fid:
                                continue
                            evidence_index.append(
                                {
                                    "id": fid,
                                    "fragment_id": fid,
                                    "interview_id": fragment_to_interview.get(fid),
                                    "category_id": None,
                                    "edge_a_id": None,
                                    "edge_b_id": None,
                                    "text": str(item.get("text", ""))[:220],
                                    "score": item.get("score"),
                                    "codes": item.get("codes", []),
                                }
                            )

                # Repairs are intentionally partial (cheap).
                if any(e.get("code") in ("CONDITIONS_ACTIONS_INVALID", "UNKNOWN_CONSTRUCTS") for e in errors):
                    repair_attempts += 1
                    repaired = await self.theory_engine.repair_conditions_actions(
                        central_cat=central_cat_data["selected_central_category"],
                        paradigm=paradigm,
                        evidence_index=evidence_index,
                        available_categories=available_category_names,
                    )
                    if repaired.get("conditions") is not None:
                        paradigm["conditions"] = repaired.get("conditions") or []
                        repairs_applied.append("conditions")
                    if repaired.get("actions") is not None:
                        paradigm["actions"] = repaired.get("actions") or []
                        repairs_applied.append("actions")

                if any(e.get("code") == "CONTEXT_INTERVENING_INVALID" for e in errors):
                    repair_attempts += 1
                    repaired_ctx = await self.theory_engine.repair_context_intervening(
                        central_cat=central_cat_data["selected_central_category"],
                        paradigm=paradigm,
                        evidence_index=evidence_index,
                        available_categories=available_category_names,
                        target_min_each=2,
                    )
                    if repaired_ctx.get("context") is not None:
                        paradigm["context"] = repaired_ctx.get("context") or []
                    if repaired_ctx.get("intervening_conditions") is not None:
                        paradigm["intervening_conditions"] = repaired_ctx.get("intervening_conditions") or []
                    repairs_applied.append("context_intervening")

                if any(e.get("code") == "CONSEQUENCES_INVALID" for e in errors):
                    repair_attempts += 1
                    repaired_consequences = await self.theory_engine.repair_consequences(
                        central_cat=central_cat_data["selected_central_category"],
                        paradigm=paradigm,
                        evidence_index=evidence_index,
                    )
                    if repaired_consequences:
                        paradigm["consequences"] = repaired_consequences
                        repairs_applied.append("consequences")
                if any(e.get("code") == "BALANCE_CONSEQUENCES" for e in errors):
                    repair_attempts += 1
                    repaired_consequences = await self.theory_engine.repair_consequences(
                        central_cat=central_cat_data["selected_central_category"],
                        paradigm=paradigm,
                        evidence_index=evidence_index,
                    )
                    if repaired_consequences:
                        paradigm["consequences"] = repaired_consequences
                        repairs_applied.append("consequences_balance")

                if any(e.get("code") == "PROPOSITIONS_INVALID" for e in errors):
                    repair_attempts += 1
                    repaired_props = await self.theory_engine.repair_propositions(
                        central_cat=central_cat_data["selected_central_category"],
                        paradigm=paradigm,
                        evidence_index=evidence_index,
                        target_count=7,
                    )
                    if repaired_props:
                        paradigm["propositions"] = repaired_props
                        repairs_applied.append("propositions")

            if not judge_result.get("ok"):
                errors = judge_result.get("errors") or []
                judge_fail_reason = ",".join(str(e.get("code")) for e in errors if e.get("code"))
                if not effective_judge_warn_only:
                    raise TheoryPipelineError("JUDGE_FAILED", str(TheoryJudgeError(judge_result))[:400])
                judge_result["warn_only"] = True
                judge_result["ok"] = True
                judge_result.setdefault("warnings", []).append(
                    {
                        "code": "JUDGE_WARN_ONLY",
                        "message": "Judge en modo warn-only: se guarda teoria con advertencias.",
                        "judge_fail_reason": judge_fail_reason,
                    }
                )

        paradigm_validation_after = self.theory_engine.validate_paradigm(paradigm)
        paradigm_llm_ms = round((perf_counter() - stage_started) * 1000.0, 2)
        self._log_stage(
            task_id,
            project_id,
            "build_straussian_paradigm",
            stage_started,
            input_tokens_estimate=paradigm_budget.get("input_tokens_estimate"),
            degradation_steps=paradigm_budget.get("degradation_steps", []),
            propositions=len(paradigm.get("propositions", []) or []),
            repairs_applied=repairs_applied,
            paradigm_validation_before=paradigm_validation_before,
            paradigm_validation_after=paradigm_validation_after,
        )

        await mark_step("analyze_saturation_and_gaps", 93)
        stage_started = perf_counter()

        def _gaps_input() -> Dict[str, Any]:
            if state.remove_evidence_step3:
                return self._strip_evidence_from_model_json(paradigm)
            return paradigm

        deterministic_gaps: Dict[str, Any] = {}
        if settings.THEORY_USE_DETERMINISTIC_GAPS:
            try:
                fragment_to_interview_for_gaps = {
                    str(ev.get("id") or ev.get("fragment_id")): str(ev.get("interview_id"))
                    for ev in evidence_index
                    if isinstance(ev, dict) and (ev.get("id") or ev.get("fragment_id")) and ev.get("interview_id")
                }
                deterministic_gaps = self._compute_deterministic_gaps(
                    critical_category_ids=[
                        str(item.get("category_id"))
                        for item in (network_metrics.get("category_centrality") or [])[:20]
                        if item.get("category_id")
                    ],
                    critical_edges=[
                        (str(item.get("category_a_id")), str(item.get("category_b_id")))
                        for item in (network_metrics.get("category_cooccurrence") or [])[:20]
                        if item.get("category_a_id") and item.get("category_b_id")
                    ],
                    category_by_id=category_by_id,
                    paradigm=paradigm,
                    evidence_index=evidence_index,
                    fragment_to_interview=fragment_to_interview_for_gaps,
                    min_interviews=min(
                        settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                        len(set(fragment_to_interview_for_gaps.values())) or settings.THEORY_EVIDENCE_MIN_INTERVIEWS,
                    ),
                )
            except Exception:
                deterministic_gaps = {}

        def _gaps_messages_builder() -> List[Dict[str, Any]]:
            return self.theory_engine.build_gaps_messages(
                theory_data=(
                    {**_gaps_input(), "deterministic_gaps": deterministic_gaps}
                    if settings.THEORY_USE_DETERMINISTIC_GAPS
                    else _gaps_input()
                ),
                template_key=template_key,
            )

        _, gaps_budget = ensure_within_budget(
            messages_builder=_gaps_messages_builder,
            model=gaps_model,
            context_limit=gaps_context_limit,
            max_output_tokens=settings.THEORY_LLM_MAX_OUTPUT_TOKENS,
            degrade_cb=state.degrade,
            margin_tokens=settings.THEORY_BUDGET_MARGIN_TOKENS,
            max_degradation_steps=settings.THEORY_BUDGET_MAX_DEGRADATION_STEPS,
        )
        logger.info(
            "[theory][%s] budget gaps fits=%s input_tokens=%s steps=%s",
            task_id,
            gaps_budget.get("fits"),
            gaps_budget.get("input_tokens_estimate"),
            gaps_budget.get("degradation_steps", []),
        )
        gaps = await self.theory_engine.analyze_saturation_and_gaps(
            (
                {**_gaps_input(), "deterministic_gaps": deterministic_gaps}
                if settings.THEORY_USE_DETERMINISTIC_GAPS
                else _gaps_input()
            ),
            template_key=template_key,
        )
        gaps_llm_ms = round((perf_counter() - stage_started) * 1000.0, 2)
        self._log_stage(
            task_id,
            project_id,
            "analyze_saturation_and_gaps",
            stage_started,
            input_tokens_estimate=gaps_budget.get("input_tokens_estimate"),
            degradation_steps=gaps_budget.get("degradation_steps", []),
            identified_gaps=len(gaps.get("identified_gaps", []) or []),
        )

        await mark_step("save_theory", 97)
        stage_started = perf_counter()

        def _section_items(key: str) -> list[dict]:
            value = paradigm.get(key) or []
            return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

        claim_sections = [
            "conditions",
            "context",
            "intervening_conditions",
            "actions",
            "consequences",
            "propositions",
        ]
        evidence_id_catalog: set[str] = set()
        for ev in evidence_index:
            if not isinstance(ev, dict):
                continue
            fid = str(ev.get("fragment_id") or ev.get("id") or "").strip()
            if fid:
                evidence_id_catalog.add(fid)
        evidence_catalog_available = len(evidence_id_catalog) > 0

        claims_by_section: Dict[str, int] = {}
        claims_count = 0
        claims_without_evidence = 0
        claims_with_resolved_evidence = 0
        claims_with_unresolved_evidence = 0
        unresolved_evidence_examples: list[dict] = []
        for section in claim_sections:
            items = _section_items(section)
            claims_by_section[section] = len(items)
            claims_count += len(items)
            for idx, item in enumerate(items):
                raw_ev = item.get("evidence_ids")
                valid_ev = [str(x).strip() for x in raw_ev] if isinstance(raw_ev, list) else []
                single_ev = item.get("evidence_id")
                if single_ev is not None and str(single_ev).strip():
                    valid_ev.append(str(single_ev).strip())
                valid_ev = [x for x in dict.fromkeys(valid_ev) if x]
                if not valid_ev:
                    claims_without_evidence += 1
                    continue
                if evidence_catalog_available:
                    if any(fid in evidence_id_catalog for fid in valid_ev):
                        claims_with_resolved_evidence += 1
                    else:
                        claims_with_unresolved_evidence += 1
                        if len(unresolved_evidence_examples) < 5:
                            unresolved_evidence_examples.append(
                                {
                                    "section": section,
                                    "order": idx,
                                    "text": str(item.get("text") or item.get("name") or "").strip(),
                                    "evidence_ids": valid_ev[:8],
                                }
                            )

        claims_with_any_evidence = max(0, claims_count - claims_without_evidence)
        claim_explain_success_count = (
            claims_with_resolved_evidence if evidence_catalog_available else claims_with_any_evidence
        )
        claim_explain_success_rate = round(claim_explain_success_count / max(1, claims_count), 3)

        evidence_interviews_covered = len(
            {str(ev.get("interview_id")) for ev in evidence_index if isinstance(ev, dict) and ev.get("interview_id")}
        )
        evidence_count = len(evidence_index)
        max_share_per_interview_observed = self._compute_max_share_per_interview(evidence_index)
        repairs_triggered_count = len(repairs_applied)
        repairs_success_rate = round((repairs_triggered_count / repair_attempts), 3) if repair_attempts > 0 else None
        quality_metrics = {
            "evidence_index_size": evidence_count,
            "distinct_interviews_in_evidence": evidence_interviews_covered,
            "max_share_per_interview": max_share_per_interview_observed,
            "judge_fail_reason": judge_fail_reason,
            "repairs_triggered_count": repairs_triggered_count,
            "repairs_success_rate": repairs_success_rate,
            "judge_available_interviews": int(judge_available_interviews or 0),
            "judge_adaptive_thresholds": bool(settings.THEORY_JUDGE_ADAPTIVE_THRESHOLDS),
            "judge_min_interviews_configured": int(settings.THEORY_EVIDENCE_MIN_INTERVIEWS),
            "judge_min_interviews_effective": int(
                ((judge_result.get("stats") or {}).get("min_interviews_effective"))
                or int(settings.THEORY_EVIDENCE_MIN_INTERVIEWS)
            ),
        }
        deterministic_routing.setdefault("execution", {})
        deterministic_routing["execution"]["network_metrics_source"] = network_metrics_source
        deterministic_routing["execution"]["semantic_evidence_source"] = semantic_evidence_source
        deterministic_routing["execution"]["network_metrics_fallback_reason"] = network_metrics_fallback_reason
        deterministic_routing["execution"]["semantic_evidence_fallback_reason"] = semantic_evidence_fallback_reason

        neo4j_claim_sync = {
            "enabled": bool(settings.THEORY_SYNC_CLAIMS_NEO4J),
            "claims_synced_count": 0,
            "neo4j_sync_failed": False,
        }
        qdrant_claim_sync = {
            "enabled": bool(settings.THEORY_SYNC_CLAIMS_QDRANT),
            "claims_synced_count": 0,
            "qdrant_sync_failed": False,
        }
        persist_evidence_max = max(50, int(settings.THEORY_EVIDENCE_INDEX_PERSIST_MAX))
        evidence_id_catalog_max = max(200, int(settings.THEORY_EVIDENCE_ID_CATALOG_MAX))

        new_theory = Theory(
            project_id=project_id,
            model_json=paradigm,
            propositions=paradigm.get("propositions", []),
            validation={
                "gap_analysis": gaps,
                "deterministic_gaps": deterministic_gaps,
                "judge": judge_result,
                "judge_rollout": judge_rollout_policy,
                "network_metrics_summary": {
                    "counts": network_metrics.get("counts", {}),
                    "category_centrality_top": network_metrics.get("category_centrality", [])[:20],
                    "category_cooccurrence_top": network_metrics.get("category_cooccurrence", [])[:30],
                    "semantic_evidence_top": semantic_evidence,
                    "edge_evidence_top": edge_evidence[:25],
                    "coarse_summary_hits": coarse_summary_hits,
                    "refined_category_count": refined_category_count,
                    "category_summary_vectors_synced": category_summary_vectors_synced,
                    "evidence_index": evidence_index[: min(persist_evidence_max, len(evidence_index))],
                    "evidence_ids": sorted(evidence_id_catalog)[:evidence_id_catalog_max],
                    "evidence_catalog_size": len(evidence_id_catalog),
                },
                "claim_metrics": {
                    "claims_count": claims_count,
                    "claims_by_section": claims_by_section,
                    "claims_without_evidence": claims_without_evidence,
                    "claims_with_any_evidence": claims_with_any_evidence,
                    "claims_with_resolved_evidence": claims_with_resolved_evidence,
                    "claims_with_unresolved_evidence": claims_with_unresolved_evidence,
                    "unresolved_evidence_examples": unresolved_evidence_examples,
                    "evidence_catalog_available": evidence_catalog_available,
                    "claim_explain_success_count": claim_explain_success_count,
                    "claim_explain_success_rate": claim_explain_success_rate,
                    "evidence_count": evidence_count,
                    "interviews_covered": evidence_interviews_covered,
                },
                "quality_metrics": quality_metrics,
                "deterministic_routing": deterministic_routing,
                "neo4j_claim_sync": neo4j_claim_sync,
                "qdrant_claim_sync": qdrant_claim_sync,
                "budget_debug": {
                    "identify": identify_budget,
                    "paradigm": paradigm_budget,
                    "gaps": gaps_budget,
                },
                "paradigm_validation": {
                    "before": paradigm_validation_before,
                    "after": paradigm_validation_after,
                    "repairs_applied": repairs_applied,
                    "evidence_index_used": evidence_index[:25],
                },
                "pipeline_runtime": {
                    "task_id": task_id,
                    "prompt_version": settings.THEORY_PROMPT_VERSION,
                    "template_key": template_key,
                    "request": request_payload,
                    "latency_ms": {
                        "category_summary_sync_ms": category_summary_sync_ms,
                        "neo4j_metrics_ms": network_metrics_elapsed_ms,
                        "qdrant_retrieval_ms": qdrant_retrieval_ms,
                        "identify_llm_ms": identify_llm_ms,
                        "paradigm_llm_ms": paradigm_llm_ms,
                        "gaps_llm_ms": gaps_llm_ms,
                    },
                },
            },
            gaps=gaps.get("identified_gaps", []),
            confidence_score=paradigm.get("confidence_score", 0.7),
            generated_by=str(settings.MODEL_REASONING_ADVANCED or settings.MODEL_CHAT or "unknown-model"),
            status="completed",
        )
        db.add(new_theory)
        await db.commit()
        await db.refresh(new_theory)
        self._log_stage(
            task_id,
            project_id,
            "save_theory",
            stage_started,
            theory_id=str(new_theory.id),
            confidence=new_theory.confidence_score,
            status=new_theory.status,
            claims_count=claims_count,
            claims_without_evidence=claims_without_evidence,
            evidence_count=evidence_count,
            interviews_covered=evidence_interviews_covered,
        )

        if settings.THEORY_SYNC_CLAIMS_NEO4J:
            try:
                await asyncio.wait_for(
                    self.neo4j_service.batch_sync_claims(
                        project_id=project_id,
                        theory_id=new_theory.id,
                        owner_id=str(user_uuid),
                        paradigm=paradigm,
                        evidence_index=evidence_index,
                        categories=[(c.id, c.name) for c in categories],
                        run_id=task_id,
                        stage="theory_pipeline",
                    ),
                    timeout=max(5, int(settings.CODING_NEO4J_SYNC_TIMEOUT_SECONDS)),
                )
                neo4j_claim_sync["claims_synced_count"] = claims_count
            except Exception as e:
                neo4j_claim_sync["neo4j_sync_failed"] = True
                logger.warning("[theory][%s] Neo4j claim sync failed: %s", task_id, str(e)[:300])

        if settings.THEORY_SYNC_CLAIMS_QDRANT:
            try:
                synced_claim_vectors = await asyncio.wait_for(
                    self._sync_claim_vectors(
                        project_id=project_id,
                        owner_id=user_uuid,
                        theory_id=new_theory.id,
                        paradigm=paradigm,
                    ),
                    timeout=max(10, int(settings.CODING_QDRANT_UPSERT_TIMEOUT_SECONDS)),
                )
                qdrant_claim_sync["claims_synced_count"] = int(synced_claim_vectors or 0)
            except Exception as e:
                qdrant_claim_sync["qdrant_sync_failed"] = True
                logger.warning("[theory][%s] Qdrant claim sync failed: %s", task_id, str(e)[:300])

        # Persist final claim sync status in validation payload.
        updated_validation = dict(new_theory.validation or {})
        updated_validation["neo4j_claim_sync"] = neo4j_claim_sync
        updated_validation["qdrant_claim_sync"] = qdrant_claim_sync
        new_theory.validation = updated_validation
        await db.commit()
        await db.refresh(new_theory)

        return {
            "id": str(new_theory.id),
            "project_id": str(new_theory.project_id),
            "version": new_theory.version,
            "status": new_theory.status,
            "confidence_score": new_theory.confidence_score,
            "generated_by": new_theory.generated_by,
            "model_json": new_theory.model_json,
            "propositions": new_theory.propositions,
            "gaps": new_theory.gaps,
            "validation": new_theory.validation,
            "created_at": new_theory.created_at.isoformat() if new_theory.created_at else None,
        }
