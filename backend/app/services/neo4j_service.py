
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from ..core.settings import settings

logger = logging.getLogger(__name__)

class FoundryNeo4jService:
    """
    Async Service for interacting with Neo4j Graph Database.
    Designed for fault tolerance: operations return gracefully if unconfigured.
    """

    def __init__(self):
        self.driver: Optional[AsyncDriver] = None
        self.enabled = False
        self._claim_constraints_checked = False

        if settings.NEO4J_URI and settings.NEO4J_USER and settings.NEO4J_PASSWORD:
            try:
                self.driver = AsyncGraphDatabase.driver(
                    settings.NEO4J_URI,
                    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                self.enabled = True
                logger.info(f"Neo4j service initialized at {settings.NEO4J_URI} as {settings.NEO4J_USER}")
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j driver: {e}")
        else:
            logger.info("Neo4j URI/User/Password not set. Graph search capabilities disabled.")

    async def verify_connectivity(self):
        """Simple check to verify if the graph database is reachable."""
        if not self.enabled or not self.driver:
            return False
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            return False

    async def create_project_node(self, project_id: UUID, name: str):
        """MERGE (p:Project {id: project_id, name: name})."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        SET p.name = $name
        RETURN p
        """
        await self._execute_write(query, {"project_id": str(project_id), "name": name})

    async def create_code_node(self, project_id: UUID, code_id: UUID, label: str):
        """MERGE (c:Code {id: code_id}) LINKED TO (p:Project)."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (c:Code {id: $code_id})
        SET c.label = $label, c.project_id = $project_id
        MERGE (p)-[:HAS_CODE]->(c)
        RETURN c
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "code_id": str(code_id),
            "label": label
        })

    async def create_interview_node(self, project_id: UUID, interview_id: UUID):
        """MERGE (i:Interview {id: interview_id}) LINKED TO (p:Project)."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (i:Interview {id: $interview_id})
        SET i.project_id = $project_id
        MERGE (p)-[:HAS_INTERVIEW]->(i)
        RETURN i
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "interview_id": str(interview_id),
        })

    async def create_fragment_node(
        self,
        project_id: UUID,
        fragment_id: UUID,
        text_snippet: str,
        *,
        interview_id: UUID | None = None,
    ):
        """MERGE (f:Fragment {id}) linked to Project (+Interview when available)."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (f:Fragment {id: $fragment_id})
        SET f.text_snippet = $text_snippet, f.project_id = $project_id
        MERGE (p)-[:HAS_FRAGMENT]->(f)
        WITH p, f
        FOREACH (_ IN CASE WHEN $interview_id IS NULL THEN [] ELSE [1] END |
            MERGE (i:Interview {id: $interview_id})
            SET i.project_id = $project_id
            MERGE (p)-[:HAS_INTERVIEW]->(i)
            MERGE (i)-[:HAS_FRAGMENT]->(f)
        )
        RETURN f
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "fragment_id": str(fragment_id),
            "text_snippet": text_snippet[:50],  # Only store snippet
            "interview_id": str(interview_id) if interview_id else None,
        })

    async def create_code_fragment_relation(
        self,
        code_id: UUID,
        fragment_id: UUID,
        *,
        confidence: float | None = None,
        source: str | None = None,
        run_id: str | None = None,
        ts: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
    ):
        """(c:Code)-[:APPLIES_TO]->(f:Fragment) + (c)-[:CODED_AS]->(f)."""
        if not self.enabled: return

        query = """
        MATCH (c:Code {id: $code_id})
        MATCH (f:Fragment {id: $fragment_id})
        MERGE (c)-[:APPLIES_TO]->(f)
        MERGE (c)-[rel:CODED_AS]->(f)
        SET rel.confidence = $confidence,
            rel.source = $source,
            rel.run_id = $run_id,
            rel.ts = $ts,
            rel.char_start = $char_start,
            rel.char_end = $char_end
        """
        await self._execute_write(query, {
            "code_id": str(code_id),
            "fragment_id": str(fragment_id),
            "confidence": confidence,
            "source": source,
            "run_id": run_id,
            "ts": ts,
            "char_start": char_start,
            "char_end": char_end,
        })

    async def create_category_node(self, project_id: UUID, category_id: UUID, name: str):
        """MERGE (cat:Category {id: category_id})."""
        if not self.enabled: return

        query = """
        MERGE (p:Project {id: $project_id})
        MERGE (cat:Category {id: $category_id})
        SET cat.name = $name
        MERGE (p)-[:HAS_CATEGORY]->(cat)
        RETURN cat
        """
        await self._execute_write(query, {
            "project_id": str(project_id),
            "category_id": str(category_id),
            "name": name
        })

    async def link_code_to_category(self, code_id: UUID, category_id: UUID):
        """(cat:Category)-[:CONTAINS]->(c:Code)."""
        if not self.enabled: return

        query = """
        MATCH (cat:Category {id: $category_id})
        MATCH (c:Code {id: $code_id})
        MERGE (cat)-[:CONTAINS]->(c)
        """
        await self._execute_write(query, {
            "code_id": str(code_id),
            "category_id": str(category_id)
        })

    async def batch_sync_taxonomy(
        self,
        project_id: UUID,
        categories: list[tuple[UUID, str]],
        code_category_pairs: list[tuple[UUID, UUID]],
    ):
        """
        Batch sync categories and category->code links using UNWIND.
        Reduces round-trips during theory generation.
        """
        if not self.enabled or not self.driver:
            return

        pid = str(project_id)
        async with self.driver.session() as session:
            if categories:
                await self._run(
                    session,
                    """
                    UNWIND $cats AS c
                    MERGE (p:Project {id: $pid})
                    MERGE (cat:Category {id: c.id})
                    SET cat.name = c.name
                    MERGE (p)-[:HAS_CATEGORY]->(cat)
                    """,
                    {
                        "pid": pid,
                        "cats": [{"id": str(cat_id), "name": name} for cat_id, name in categories],
                    },
                )

            if code_category_pairs:
                await self._run(
                    session,
                    """
                    UNWIND $pairs AS p
                    MATCH (cat:Category {id: p.category_id})
                    MATCH (c:Code {id: p.code_id})
                    MERGE (cat)-[:CONTAINS]->(c)
                    """,
                    {
                        "pairs": [
                            {"code_id": str(code_id), "category_id": str(category_id)}
                            for code_id, category_id in code_category_pairs
                        ]
                    },
                )

    async def batch_sync_interview(
        self,
        project_id: UUID,
        interview_id: UUID | None,
        fragments: list[tuple[UUID, str]],
        codes_cache: dict,
        fragment_code_pairs: list[tuple[UUID, UUID]],
        code_edge_rows: list[dict[str, Any]] | None = None,
    ):
        """
        V2 sync:
        - Materializes Interview nodes/links.
        - Keeps APPLIES_TO compatibility.
        - Adds auditable CODED_AS edges with coding metadata.
        """
        if not self.enabled or not self.driver:
            return

        pid = str(project_id)
        iid = str(interview_id) if interview_id else None
        now_iso = datetime.utcnow().isoformat()
        async with self.driver.session() as session:
            if iid:
                await self._run(
                    session,
                    """
                    MERGE (proj:Project {id: $pid})
                    MERGE (iv:Interview {id: $iid})
                    SET iv.project_id = $pid
                    MERGE (proj)-[:HAS_INTERVIEW]->(iv)
                    """,
                    {"pid": pid, "iid": iid},
                )

            if fragments:
                if iid:
                    await self._run(
                        session,
                        """
                        UNWIND $frags AS f
                        MERGE (proj:Project {id: $pid})
                        MATCH (iv:Interview {id: $iid})
                        MERGE (fr:Fragment {id: f.id})
                        SET fr.text_snippet = f.snippet, fr.project_id = $pid
                        MERGE (proj)-[:HAS_FRAGMENT]->(fr)
                        MERGE (iv)-[:HAS_FRAGMENT]->(fr)
                        """,
                        {
                            "pid": pid,
                            "iid": iid,
                            "frags": [{"id": str(fid), "snippet": text[:50]} for fid, text in fragments],
                        },
                    )
                else:
                    await self._run(
                        session,
                        """
                        UNWIND $frags AS f
                        MERGE (proj:Project {id: $pid})
                        MERGE (fr:Fragment {id: f.id})
                        SET fr.text_snippet = f.snippet, fr.project_id = $pid
                        MERGE (proj)-[:HAS_FRAGMENT]->(fr)
                        """,
                        {
                            "pid": pid,
                            "frags": [{"id": str(fid), "snippet": text[:50]} for fid, text in fragments],
                        },
                    )

            if codes_cache:
                await self._run(
                    session,
                    """
                    UNWIND $codes AS c
                    MERGE (proj:Project {id: $pid})
                    MERGE (co:Code {id: c.id})
                    SET co.label = c.label, co.project_id = $pid
                    MERGE (proj)-[:HAS_CODE]->(co)
                    """,
                    {
                        "pid": pid,
                        "codes": [{"id": str(obj.id), "label": label} for label, obj in codes_cache.items()],
                    },
                )

            rows: list[dict[str, Any]] = []
            if code_edge_rows:
                for row in code_edge_rows:
                    if not isinstance(row, dict):
                        continue
                    code_id = str(row.get("code_id") or "").strip()
                    frag_id = str(row.get("frag_id") or row.get("fragment_id") or "").strip()
                    if not code_id or not frag_id:
                        continue
                    rows.append(
                        {
                            "code_id": code_id,
                            "frag_id": frag_id,
                            "confidence": row.get("confidence"),
                            "source": row.get("source"),
                            "run_id": row.get("run_id"),
                            "ts": row.get("ts") or now_iso,
                            "char_start": row.get("char_start"),
                            "char_end": row.get("char_end"),
                        }
                    )
            elif fragment_code_pairs:
                rows = [
                    {
                        "code_id": str(cid),
                        "frag_id": str(fid),
                        "confidence": None,
                        "source": None,
                        "run_id": None,
                        "ts": now_iso,
                        "char_start": None,
                        "char_end": None,
                    }
                    for fid, cid in fragment_code_pairs
                ]

            if rows:
                await self._run(
                    session,
                    """
                    UNWIND $pairs AS p
                    MATCH (c:Code {id: p.code_id})
                    MATCH (f:Fragment {id: p.frag_id})
                    MERGE (c)-[:APPLIES_TO]->(f)
                    MERGE (c)-[rel:CODED_AS]->(f)
                    SET rel.confidence = p.confidence,
                        rel.source = p.source,
                        rel.run_id = p.run_id,
                        rel.ts = p.ts,
                        rel.char_start = p.char_start,
                        rel.char_end = p.char_end
                    """,
                    {"pairs": rows},
                )

    async def batch_sync_claims(
        self,
        *,
        project_id: UUID,
        theory_id: UUID,
        owner_id: str,
        paradigm: Dict[str, Any],
        evidence_index: List[Dict[str, Any]],
        categories: list[tuple[UUID, str]],
        run_id: str | None = None,
        stage: str | None = "theory_generation",
    ) -> None:
        """
        Best-effort: persist auditable theory units as Claim nodes with SUPPORTED_BY edges.

        This is intentionally derived data:
        - Postgres remains the source of truth.
        - Neo4j stores a traceable symbolic memory for explainability and UI ("Ver evidencia").
        """
        if not self.enabled or not self.driver:
            return

        await self._ensure_claim_constraints()

        pid = str(project_id)
        tid = str(theory_id)
        oid = str(owner_id or "")

        # Deterministic mapping from category name -> category_id for ABOUT edges.
        cat_by_name = {name.strip().lower(): str(cid) for cid, name in categories if name}

        evidence_score_by_fragment: dict[str, float] = {}
        for ev in evidence_index or []:
            fid = str(ev.get("fragment_id") or ev.get("id") or "").strip()
            if not fid:
                continue
            try:
                evidence_score_by_fragment[fid] = float(ev.get("score", 0.0))
            except Exception:
                continue

        def _claim_id(kind: str, order: int, text: str) -> str:
            # Stable id per theory + section + order + text.
            base = f"{tid}:{kind}:{order}:{(text or '').strip()}"
            return str(uuid.uuid5(uuid.UUID(tid), base))

        def _items(section: str) -> list[dict]:
            raw = paradigm.get(section) or []
            return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

        now_iso = None
        try:
            # Avoid importing datetime; keep lightweight.
            now_iso = __import__("datetime").datetime.utcnow().isoformat()
        except Exception:
            now_iso = None

        claims: list[dict] = []
        about_rows: list[dict] = []
        support_rows: list[dict] = []
        contradict_rows: list[dict] = []
        run_id_norm = str(run_id).strip() if run_id else None
        stage_norm = str(stage).strip() if stage else "theory_generation"

        def _push_section(section: str, claim_type: str, text_key: str = "name") -> None:
            for i, item in enumerate(_items(section)):
                text = str(item.get(text_key) or item.get("text") or "").strip()
                if not text:
                    continue
                cid = _claim_id(claim_type, i, text)
                claims.append(
                    {
                        "id": cid,
                        "type": claim_type,
                        "section": section,
                        "order": i,
                        "text": text[:2000],
                        "created_at": now_iso,
                        "run_id": run_id_norm,
                        "stage": stage_norm,
                    }
                )

                name_for_about = str(item.get("name") or "").strip().lower()
                cat_id = cat_by_name.get(name_for_about)
                if cat_id:
                    about_rows.append({"claim_id": cid, "category_id": cat_id})

                ev_ids = item.get("evidence_ids") or []
                if isinstance(ev_ids, list):
                    rank = 0
                    for fid in ev_ids:
                        frag_id = str(fid).strip()
                        if not frag_id:
                            continue
                        support_rows.append(
                            {
                                "claim_id": cid,
                                "fragment_id": frag_id,
                                "rank": rank,
                                "score": evidence_score_by_fragment.get(frag_id, 0.0),
                            }
                        )
                        rank += 1

                contra_ids = (
                    item.get("counter_evidence_ids")
                    or item.get("contradicted_by_ids")
                    or item.get("contrast_evidence_ids")
                    or []
                )
                if isinstance(contra_ids, list):
                    rank = 0
                    for fid in contra_ids:
                        frag_id = str(fid).strip()
                        if not frag_id:
                            continue
                        contradict_rows.append(
                            {
                                "claim_id": cid,
                                "fragment_id": frag_id,
                                "rank": rank,
                                "score": evidence_score_by_fragment.get(frag_id, 0.0),
                            }
                        )
                        rank += 1

        _push_section("conditions", "condition", text_key="name")
        _push_section("context", "condition", text_key="name")
        _push_section("intervening_conditions", "condition", text_key="name")
        _push_section("actions", "action", text_key="name")
        _push_section("consequences", "consequence", text_key="name")
        _push_section("propositions", "proposition", text_key="text")

        if not claims:
            return

        async with self.driver.session() as session:
            # Claim nodes
            await self._run(
                session,
                """
                UNWIND $claims AS c
                MERGE (p:Project {id: $pid})
                MERGE (cl:Claim {id: c.id})
                SET cl.project_id = $pid,
                    cl.theory_id = $tid,
                    cl.owner_id = $oid,
                    cl.claim_type = c.type,
                    cl.section = c.section,
                    cl.`order` = c.order,
                    cl.text = c.text,
                    cl.created_at = c.created_at,
                    cl.run_id = c.run_id,
                    cl.stage = c.stage
                MERGE (p)-[:HAS_CLAIM]->(cl)
                """,
                {"pid": pid, "tid": tid, "oid": oid, "claims": claims},
            )

            if about_rows:
                await self._run(
                    session,
                    """
                    UNWIND $rows AS r
                    MATCH (cl:Claim {id: r.claim_id})
                    MATCH (cat:Category {id: r.category_id})
                    MERGE (cl)-[:ABOUT]->(cat)
                    """,
                    {"rows": about_rows},
                )

            if support_rows:
                await self._run(
                    session,
                    """
                    UNWIND $rows AS r
                    MATCH (cl:Claim {id: r.claim_id})
                    MATCH (f:Fragment {id: r.fragment_id})
                    MERGE (cl)-[sb:SUPPORTED_BY]->(f)
                    SET sb.rank = r.rank,
                        sb.score = r.score
                    """,
                    {"rows": support_rows},
                )

            if contradict_rows:
                await self._run(
                    session,
                    """
                    UNWIND $rows AS r
                    MATCH (cl:Claim {id: r.claim_id})
                    MATCH (f:Fragment {id: r.fragment_id})
                    MERGE (cl)-[cb:CONTRADICTED_BY]->(f)
                    SET cb.rank = r.rank,
                        cb.score = r.score
                    """,
                    {"rows": contradict_rows},
                )

    async def _materialize_category_cooccurrence(self, project_id: str) -> None:
        """
        Materialize Category-[:CO_OCCURS_WITH] edges from coded fragment overlap.
        """
        if not self.enabled or not self.driver:
            return
        now_iso = datetime.utcnow().isoformat()
        query = """
        MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(c1:Category)-[:CONTAINS]->(:Code)-[:APPLIES_TO]->(f:Fragment)<-[:APPLIES_TO]-(:Code)<-[:CONTAINS]-(c2:Category)
        WHERE c1.id < c2.id
        WITH c1, c2, count(DISTINCT f) AS shared
        WHERE shared > 0
        WITH c1, c2, shared, toFloat(shared) AS weight
        MERGE (c1)-[r:CO_OCCURS_WITH]->(c2)
        SET r.count = shared,
            r.weight = weight,
            r.project_id = $project_id,
            r.updated_at = $updated_at
        MERGE (c2)-[r2:CO_OCCURS_WITH]->(c1)
        SET r2.count = shared,
            r2.weight = weight,
            r2.project_id = $project_id,
            r2.updated_at = $updated_at
        """
        await self._execute_write(
            query,
            {
                "project_id": project_id,
                "updated_at": now_iso,
            },
        )

    async def _ensure_claim_constraints(self) -> None:
        """
        Best-effort uniqueness constraints for claim graph idempotency.
        """
        if not self.enabled or not self.driver or self._claim_constraints_checked:
            return
        try:
            async with self.driver.session() as session:
                await self._run(
                    session,
                    """
                    CREATE CONSTRAINT claim_id_unique IF NOT EXISTS
                    FOR (cl:Claim)
                    REQUIRE cl.id IS UNIQUE
                    """,
                    {},
                )
                await self._run(
                    session,
                    """
                    CREATE CONSTRAINT interview_id_unique IF NOT EXISTS
                    FOR (iv:Interview)
                    REQUIRE iv.id IS UNIQUE
                    """,
                    {},
                )
            self._claim_constraints_checked = True
        except Exception as e:
            logger.warning("Neo4j claim constraint setup skipped: %s", str(e)[:300])

    async def ensure_project_node(self, project_id: UUID, name: str = "Unnamed Project"):
        """Ensures a project node exists before syncing related entities."""
        if not self.enabled:
            raise RuntimeError("Neo4j service is not enabled")
        await self.create_project_node(project_id, name or "Unnamed Project")

    async def get_project_network_metrics(self, project_id: UUID) -> Dict[str, Any]:
        """
        Returns graph metrics used by theory generation.
        Raises when project has no usable graph data.
        """
        if not self.enabled or not self.driver:
            raise RuntimeError("Neo4j service is not enabled")

        project_id_str = str(project_id)
        try:
            await self._materialize_category_cooccurrence(project_id_str)
        except Exception as e:
            logger.warning("Neo4j cooccurrence materialization skipped: %s", str(e)[:300])

        counts_query = """
        MATCH (p:Project {id: $project_id})
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        WITH p, count(DISTINCT cat) AS category_count
        OPTIONAL MATCH (p)-[:HAS_CODE]->(c:Code)
        WITH p, category_count, count(DISTINCT c) AS code_count
        OPTIONAL MATCH (p)-[:HAS_FRAGMENT]->(f:Fragment)
        RETURN category_count, code_count, count(DISTINCT f) AS fragment_count
        """

        centrality_query = """
        MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (cat)-[:CONTAINS]->(c:Code)-[:APPLIES_TO]->(:Fragment)<-[:APPLIES_TO]-(other:Code)
        WITH cat, count(DISTINCT c) AS code_degree, count(DISTINCT other) AS fragment_degree
        RETURN cat.id AS category_id, cat.name AS category_name, code_degree, fragment_degree
        ORDER BY code_degree DESC, fragment_degree DESC
        """

        cooccurrence_query = """
        MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(c1:Category)-[co:CO_OCCURS_WITH]->(c2:Category)
        WHERE c1.id < c2.id
          AND co.project_id = $project_id
        RETURN c1.id AS category_a_id, c1.name AS category_a_name,
               c2.id AS category_b_id, c2.name AS category_b_name,
               co.count AS shared_fragments
        ORDER BY shared_fragments DESC
        """

        counts_data = await self._execute_read(counts_query, {"project_id": project_id_str})
        centrality_data = await self._execute_read(centrality_query, {"project_id": project_id_str})
        cooccurrence_data = await self._execute_read(cooccurrence_query, {"project_id": project_id_str})

        counts = counts_data[0] if counts_data else {
            "category_count": 0,
            "code_count": 0,
            "fragment_count": 0
        }

        if counts.get("category_count", 0) == 0:
            raise ValueError(f"No category nodes found in Neo4j for project {project_id_str}")

        gds_meta: Dict[str, Any] = {"enabled": False}
        pagerank_by_id: Dict[str, float] = {}
        degree_by_id: Dict[str, float] = {}

        # Optional: use Neo4j Graph Data Science if installed.
        # Falls back silently to Cypher-only metrics if GDS procedures are unavailable.
        try:
            if self.enabled and self.driver:
                graph_name = f"theogen_cat_{project_id_str.replace('-', '')[:8]}_{uuid.uuid4().hex[:6]}"
                graph_created = False
                node_query = """
                MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(cat:Category)
                RETURN id(cat) AS id, cat.id AS category_id, cat.name AS category_name
                """
                rel_query = """
                MATCH (:Project {id: $project_id})-[:HAS_CATEGORY]->(c1:Category)-[co:CO_OCCURS_WITH]->(c2:Category)
                WHERE id(c1) < id(c2) AND co.project_id = $project_id
                RETURN id(c1) AS source, id(c2) AS target, toFloat(co.weight) AS weight
                """

                async with self.driver.session() as session:
                    # Detect GDS availability.
                    await self._run(session, "CALL gds.version() YIELD version RETURN version", {})

                    try:
                        await self._run(
                            session,
                            """
                            CALL gds.graph.project.cypher(
                              $graph_name,
                              $node_query,
                              $rel_query,
                              {validateRelationships: false}
                            )
                            YIELD graphName, nodeCount, relationshipCount
                            """,
                            {
                                "graph_name": graph_name,
                                "project_id": project_id_str,
                                "node_query": node_query,
                                "rel_query": rel_query,
                            },
                        )
                        graph_created = True

                        pr_res = await self._run(
                            session,
                            """
                            CALL gds.pageRank.stream($graph_name, {relationshipWeightProperty: 'weight'})
                            YIELD nodeId, score
                            RETURN gds.util.asNode(nodeId).id AS category_id,
                                   gds.util.asNode(nodeId).name AS category_name,
                                   score
                            ORDER BY score DESC
                            """,
                            {"graph_name": graph_name},
                        )
                        pagerank_rows = await pr_res.data()

                        deg_res = await self._run(
                            session,
                            """
                            CALL gds.degree.stream($graph_name, {relationshipWeightProperty: 'weight'})
                            YIELD nodeId, score
                            RETURN gds.util.asNode(nodeId).id AS category_id,
                                   gds.util.asNode(nodeId).name AS category_name,
                                   score
                            ORDER BY score DESC
                            """,
                            {"graph_name": graph_name},
                        )
                        degree_rows = await deg_res.data()
                    finally:
                        if graph_created:
                            try:
                                await self._run(
                                    session,
                                    "CALL gds.graph.drop($graph_name, false)",
                                    {"graph_name": graph_name},
                                )
                            except Exception:
                                # Best-effort cleanup; do not fail the request for a drop issue.
                                pass

                pagerank_by_id = {
                    str(r.get("category_id", "")): float(r.get("score", 0.0))
                    for r in pagerank_rows
                    if r.get("category_id") is not None
                }
                degree_by_id = {
                    str(r.get("category_id", "")): float(r.get("score", 0.0))
                    for r in degree_rows
                    if r.get("category_id") is not None
                }
                gds_meta = {
                    "enabled": True,
                    "pagerank_rows": pagerank_rows,
                    "degree_rows": degree_rows,
                }
        except Exception as e:
            # GDS not installed / blocked / insufficient permissions.
            gds_meta = {"enabled": False, "error": str(e)[:300]}

        # Enrich centrality rows and (when available) prefer algorithmic rank ordering.
        for row in centrality_data:
            cid = str(row.get("category_id", ""))
            if cid:
                if cid in pagerank_by_id:
                    row["pagerank"] = pagerank_by_id[cid]
                if cid in degree_by_id:
                    row["gds_degree"] = degree_by_id[cid]

        if gds_meta.get("enabled"):
            centrality_data = sorted(
                centrality_data,
                key=lambda r: (
                    -(float(r.get("pagerank", 0.0)) if r.get("pagerank") is not None else 0.0),
                    -(float(r.get("gds_degree", 0.0)) if r.get("gds_degree") is not None else 0.0),
                    -(float(r.get("code_degree", 0.0)) if r.get("code_degree") is not None else 0.0),
                    -(float(r.get("fragment_degree", 0.0)) if r.get("fragment_degree") is not None else 0.0),
                ),
            )

        return {
            "project_id": project_id_str,
            "counts": counts,
            "category_centrality": centrality_data,
            "category_cooccurrence": cooccurrence_data,
            "gds": gds_meta,
        }

    async def get_theory_claims_explain(
        self,
        *,
        project_id: UUID,
        theory_id: UUID,
        owner_id: UUID,
        limit: int = 500,
        offset: int = 0,
        section: str | None = None,
        claim_type: str | None = None,
    ) -> Dict[str, Any]:
        """
        Explainability read model for UI:
        Category -> Claim -> Fragment paths persisted in Neo4j.
        """
        if not self.enabled or not self.driver:
            return {"total": 0, "claims": []}

        section_norm = (section or "").strip().lower() or None
        claim_type_norm = (claim_type or "").strip().lower() or None

        count_query = """
        MATCH (p:Project {id: $project_id})-[:HAS_CLAIM]->(cl:Claim)
        WHERE cl.project_id = $project_id
          AND cl.theory_id = $theory_id
          AND cl.owner_id = $owner_id
          AND ($section IS NULL OR cl.section = $section)
          AND ($claim_type IS NULL OR cl.claim_type = $claim_type)
        RETURN count(cl) AS total
        """
        count_rows = await self._execute_read(
            count_query,
            {
                "project_id": str(project_id),
                "theory_id": str(theory_id),
                "owner_id": str(owner_id),
                "section": section_norm,
                "claim_type": claim_type_norm,
            },
        )
        total = int((count_rows[0] or {}).get("total", 0)) if count_rows else 0

        query = """
        MATCH (p:Project {id: $project_id})-[:HAS_CLAIM]->(cl:Claim)
        WHERE cl.project_id = $project_id
          AND cl.theory_id = $theory_id
          AND cl.owner_id = $owner_id
          AND ($section IS NULL OR cl.section = $section)
          AND ($claim_type IS NULL OR cl.claim_type = $claim_type)
        OPTIONAL MATCH (cl)-[:ABOUT]->(cat:Category)
        WITH cl, collect(DISTINCT {id: cat.id, name: cat.name}) AS categories
        OPTIONAL MATCH (cl)-[sb:SUPPORTED_BY]->(f:Fragment)
        WITH cl, categories,
             collect(DISTINCT {
               fragment_id: f.id,
               text: f.text_snippet,
               score: sb.score,
               rank: sb.rank
             }) AS evidence
        OPTIONAL MATCH (cl)-[cb:CONTRADICTED_BY]->(cf:Fragment)
        WITH cl, categories, evidence,
             collect(DISTINCT {
               fragment_id: cf.id,
               text: cf.text_snippet,
               score: cb.score,
               rank: cb.rank
             }) AS counter_evidence
        RETURN
          cl.id AS claim_id,
          cl.claim_type AS claim_type,
          cl.section AS section,
          cl.`order` AS ord,
          cl.text AS text,
          categories,
          evidence,
          counter_evidence
        ORDER BY
          CASE cl.section
            WHEN 'conditions' THEN 1
            WHEN 'context' THEN 2
            WHEN 'intervening_conditions' THEN 3
            WHEN 'actions' THEN 4
            WHEN 'consequences' THEN 5
            WHEN 'propositions' THEN 6
            ELSE 99
          END ASC,
          cl.`order` ASC
        SKIP $offset
        LIMIT $limit
        """
        rows = await self._execute_read(
            query,
            {
                "project_id": str(project_id),
                "theory_id": str(theory_id),
                "owner_id": str(owner_id),
                "section": section_norm,
                "claim_type": claim_type_norm,
                "offset": max(0, int(offset)),
                "limit": max(1, int(limit)),
            },
        )

        normalized: List[Dict[str, Any]] = []
        for row in rows:
            categories = []
            for cat in (row.get("categories") or []):
                if not isinstance(cat, dict):
                    continue
                if not cat.get("id") and not cat.get("name"):
                    continue
                categories.append(
                    {
                        "id": str(cat.get("id") or ""),
                        "name": str(cat.get("name") or ""),
                    }
                )

            evidence = []
            for ev in (row.get("evidence") or []):
                if not isinstance(ev, dict):
                    continue
                fragment_id = str(ev.get("fragment_id") or "").strip()
                if not fragment_id:
                    continue
                evidence.append(
                    {
                        "fragment_id": fragment_id,
                        "text": str(ev.get("text") or ""),
                        "score": ev.get("score"),
                        "rank": ev.get("rank"),
                    }
                )

            counter_evidence = []
            for ev in (row.get("counter_evidence") or []):
                if not isinstance(ev, dict):
                    continue
                fragment_id = str(ev.get("fragment_id") or "").strip()
                if not fragment_id:
                    continue
                counter_evidence.append(
                    {
                        "fragment_id": fragment_id,
                        "text": str(ev.get("text") or ""),
                        "score": ev.get("score"),
                        "rank": ev.get("rank"),
                    }
                )

            normalized.append(
                {
                    "claim_id": str(row.get("claim_id") or ""),
                    "claim_type": str(row.get("claim_type") or ""),
                    "section": str(row.get("section") or ""),
                    "order": int(row.get("ord") or 0),
                    "text": str(row.get("text") or ""),
                    "categories": categories,
                    "evidence": evidence,
                    "counter_evidence": counter_evidence,
                }
            )
        return {"total": total, "claims": normalized}

    async def close(self):
        """Closes the Neo4j driver connection."""
        if self.driver:
            await self.driver.close()

    async def _run(self, session: AsyncSession, query: str, parameters: Dict[str, Any]):
        """
        Run a Cypher query with a best-effort server-side timeout.
        Falls back gracefully if the installed driver version doesn't support the timeout kwarg.
        """
        timeout_s = max(5, int(getattr(settings, "NEO4J_QUERY_TIMEOUT_SECONDS", 120)))
        try:
            return await session.run(query, parameters, timeout=timeout_s)
        except TypeError:
            return await session.run(query, parameters)

    async def _execute_write(self, query: str, parameters: Dict[str, Any]):
        """Internal helper to execute write transactions safely."""
        try:
            async with self.driver.session() as session:
                await self._run(session, query, parameters)
        except Exception as e:
            logger.error(f"Neo4j write failed: {e}")
            raise

    async def _execute_read(self, query: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Internal helper to execute read queries and return plain dict rows."""
        try:
            async with self.driver.session() as session:
                result = await self._run(session, query, parameters)
                return await result.data()
        except Exception as e:
            logger.error(f"Neo4j read failed: {e}")
            raise

neo4j_service = FoundryNeo4jService()

