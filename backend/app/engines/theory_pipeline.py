from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.settings import settings
from ..models.models import Category, Code, Interview, Project, Theory
from ..schemas.theory import TheoryGenerateRequest
from ..services.azure_openai import foundry_openai
from ..services.neo4j_service import neo4j_service
from ..services.qdrant_service import qdrant_service
from ..utils.token_budget import ensure_within_budget
from .coding_engine import coding_engine
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
                        await self.coding_engine.auto_code_interview(project_id, iv_id, iv_db)

            await asyncio.gather(*[_code_interview(iv.id) for iv in completed_interviews])
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
        await self.neo4j_service.ensure_project_node(project_id, project.name)
        codes = (
            await db.execute(select(Code).filter(Code.project_id == project_id))
        ).scalars().all()
        await self.neo4j_service.batch_sync_taxonomy(
            project_id=project_id,
            categories=[(cat.id, cat.name) for cat in categories],
            code_category_pairs=[(code.id, code.category_id) for code in codes if code.category_id],
        )
        self._log_stage(
            task_id,
            project_id,
            "neo4j_taxonomy_sync",
            stage_started,
            categories=len(categories),
            codes=len(codes),
        )

        await mark_step("network_metrics", 60)
        stage_started = perf_counter()
        network_metrics = await self.neo4j_service.get_project_network_metrics(project_id)
        self._log_stage(
            task_id,
            project_id,
            "network_metrics",
            stage_started,
            counts=network_metrics.get("counts", {}),
            centrality=len(network_metrics.get("category_centrality", [])),
            cooccurrence=len(network_metrics.get("category_cooccurrence", [])),
        )

        await mark_step("semantic_evidence", 70)
        stage_started = perf_counter()
        category_by_id = {str(c.id): c for c in categories}
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
        self._log_stage(
            task_id,
            project_id,
            "semantic_evidence",
            stage_started,
            candidate_categories=len(top_categories),
            categories_with_evidence=len(semantic_evidence),
            total_fragments=sum(len(item.get("fragments", [])) for item in semantic_evidence),
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
        )
        paradigm = self.theory_engine.normalize_paradigm(
            paradigm,
            central_cat=central_cat_data["selected_central_category"],
        )

        evidence_index: List[Dict[str, Any]] = []
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
                        "category_id": cat.get("id"),
                        "category_name": cat.get("name"),
                        "text": str(frag.get("text", ""))[:220],
                        "score": frag.get("score"),
                    }
                )

        paradigm_validation_before = self.theory_engine.validate_paradigm(paradigm)
        repairs_applied: List[str] = []
        available_category_names = [
            str(c.get("name")) for c in (cats_data or []) if isinstance(c, dict) and c.get("name")
        ]
        if not paradigm_validation_before.get("consequences_ok"):
            try:
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

        paradigm_validation_after = self.theory_engine.validate_paradigm(paradigm)
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

        def _gaps_messages_builder() -> List[Dict[str, Any]]:
            return self.theory_engine.build_gaps_messages(
                theory_data=_gaps_input(),
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
            _gaps_input(),
            template_key=template_key,
        )
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
        new_theory = Theory(
            project_id=project_id,
            model_json=paradigm,
            propositions=paradigm.get("propositions", []),
            validation={
                "gap_analysis": gaps,
                "network_metrics_summary": {
                    "counts": network_metrics.get("counts", {}),
                    "category_centrality_top": network_metrics.get("category_centrality", [])[:20],
                    "category_cooccurrence_top": network_metrics.get("category_cooccurrence", [])[:30],
                    "semantic_evidence_top": semantic_evidence,
                },
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
                },
            },
            gaps=gaps.get("identified_gaps", []),
            confidence_score=paradigm.get("confidence_score", 0.7),
            generated_by="DeepSeek-V3.2-Speciale/Kimi-K2.5",
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
        )

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
