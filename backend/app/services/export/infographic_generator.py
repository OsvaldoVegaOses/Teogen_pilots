from __future__ import annotations

import math
import textwrap
from io import BytesIO
from typing import Any, Dict, List

import networkx as nx
from PIL import Image, ImageDraw, ImageFont


class InfographicGenerator:
    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        if isinstance(value, list):
            return " | ".join([InfographicGenerator._as_text(v) for v in value if v is not None])
        if isinstance(value, dict):
            # Consequence objects: format cleanly for visual outputs.
            if "name" in value and ("type" in value or "horizon" in value):
                name = value.get("name") or value.get("description") or value.get("text") or ""
                ctype = value.get("type") or ""
                horizon = value.get("horizon") or ""
                tags = "/".join([t for t in [ctype, horizon] if t])
                return f"{name} [{tags}]" if tags else str(name)

            for key in ("text", "description", "definition", "name"):
                if key in value and value[key] is not None:
                    return str(value[key])
            return str(value)
        return str(value)

    @staticmethod
    def _bullet_lines(value: Any, limit: int = 4) -> List[str]:
        lines: List[str] = []
        if isinstance(value, list):
            source = value
        else:
            source = [value]

        for item in source:
            text = InfographicGenerator._as_text(item).strip()
            if text:
                lines.append(f"- {text}")
            if len(lines) >= limit:
                break
        return lines

    def _font(self, size: int):
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def _draw_wrapped_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        width_chars: int,
        line_height: int,
        font,
        fill,
        max_lines: int,
    ) -> int:
        lines = textwrap.wrap(text or "", width=width_chars)
        lines = lines[:max_lines]
        for line in lines:
            draw.text((x, y), line, fill=fill, font=font)
            y += line_height
        return y

    @staticmethod
    def _coerce_float(val: Any, default: float = 0.0) -> float:
        try:
            if val is None:
                return default
            return float(val)
        except Exception:
            return default

    def _build_category_graph(self, summary: Dict[str, Any]) -> nx.Graph | None:
        nodes = summary.get("category_centrality_top", []) or []
        edges = summary.get("category_cooccurrence_top", []) or []
        if not nodes and not edges:
            return None

        g = nx.Graph()

        for row in nodes:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("category_id") or "").strip()
            name = str(row.get("category_name") or "").strip()
            if not cid or not name:
                continue
            score = (
                self._coerce_float(row.get("pagerank"), 0.0)
                or self._coerce_float(row.get("gds_degree"), 0.0)
                or self._coerce_float(row.get("code_degree"), 0.0) + self._coerce_float(row.get("fragment_degree"), 0.0)
            )
            g.add_node(cid, label=name, score=score)

        for row in edges:
            if not isinstance(row, dict):
                continue
            a = str(row.get("category_a_id") or "").strip()
            b = str(row.get("category_b_id") or "").strip()
            if not a or not b or a == b:
                continue
            w = max(1.0, self._coerce_float(row.get("shared_fragments"), 1.0))

            if a not in g.nodes:
                g.add_node(a, label=str(row.get("category_a_name") or a), score=1.0)
            if b not in g.nodes:
                g.add_node(b, label=str(row.get("category_b_name") or b), score=1.0)
            g.add_edge(a, b, weight=w)

        if g.number_of_nodes() == 0:
            return None
        return g

    def _draw_network_panel(
        self,
        img: Image.Image,
        rect: tuple[int, int, int, int],
        central_label: str,
        summary: Dict[str, Any],
        section_font,
        body_font,
    ) -> None:
        draw = ImageDraw.Draw(img)
        x0, y0, x1, y1 = rect

        draw.rounded_rectangle((x0, y0, x1, y1), radius=20, fill=(250, 250, 255), outline=(147, 172, 219), width=2)
        draw.text((x0 + 20, y0 + 18), "Red de categorias (Neo4j)", fill=(37, 63, 104), font=section_font)

        g = self._build_category_graph(summary)
        if not g or g.number_of_nodes() == 0:
            self._draw_wrapped_text(draw, "- Sin datos de red", x0 + 20, y0 + 70, 80, 26, body_font, (52, 68, 96), 2)
            return

        if g.number_of_edges() == 0:
            top = []
            for row in (summary.get("category_centrality_top", []) or [])[:10]:
                if isinstance(row, dict) and row.get("category_name"):
                    top.append(f"- {row.get('category_name')}")
            if not top:
                top = ["- Sin datos de coocurrencia"]
            self._draw_wrapped_text(draw, "Top categorias:\n" + "\n".join(top), x0 + 20, y0 + 70, 80, 26, body_font, (52, 68, 96), 12)
            return

        # Deterministic layout for stable exports.
        try:
            pos = nx.spring_layout(
                g,
                weight="weight",
                seed=42,
                k=0.85 / math.sqrt(max(1, g.number_of_nodes())),
            )
        except Exception:
            pos = nx.circular_layout(g)

        pad = 35
        gx0, gy0, gx1, gy1 = x0 + pad, y0 + 70, x1 - pad, y1 - pad
        w = max(1, gx1 - gx0)
        h = max(1, gy1 - gy0)

        xs = [float(p[0]) for p in pos.values()]
        ys = [float(p[1]) for p in pos.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        dx = max(1e-9, maxx - minx)
        dy = max(1e-9, maxy - miny)

        def to_px(p):
            px = gx0 + int((float(p[0]) - minx) / dx * w)
            py = gy0 + int((float(p[1]) - miny) / dy * h)
            return px, py

        # Pick a "central" node: label match first, else max score.
        target_id = None
        central_cf = (central_label or "").casefold().strip()
        if central_cf:
            for nid, data in g.nodes(data=True):
                if str(data.get("label", "")).casefold().strip() == central_cf:
                    target_id = nid
                    break
        if not target_id:
            target_id = max(g.nodes, key=lambda n: float(g.nodes[n].get("score", 0.0)))

        scores = [float(data.get("score", 0.0)) for _, data in g.nodes(data=True)]
        max_score = max(scores) if scores else 1.0
        weights = [float(data.get("weight", 1.0)) for _, _, data in g.edges(data=True)]
        max_w = max(weights) if weights else 1.0

        # Edges first (under nodes).
        for a, b, data in g.edges(data=True):
            ax, ay = to_px(pos[a])
            bx, by = to_px(pos[b])
            ww = float(data.get("weight", 1.0))
            lw = 1 + int(4 * (ww / max_w))
            draw.line((ax, ay, bx, by), fill=(150, 170, 205), width=lw)

        # Nodes + labels.
        for nid, data in g.nodes(data=True):
            px, py = to_px(pos[nid])
            score = float(data.get("score", 0.0))
            r = 10 + int(22 * (score / max_score))
            fill = (255, 235, 205) if nid == target_id else (230, 241, 255)
            outline = (225, 156, 88) if nid == target_id else (63, 114, 175)
            draw.ellipse((px - r, py - r, px + r, py + r), fill=fill, outline=outline, width=3)

            label = str(data.get("label", nid))
            label = (label[:22] + "...") if len(label) > 25 else label
            draw.text((px + r + 6, py - 10), label, fill=(35, 52, 88), font=body_font)

        legend = "Tamano nodo: centralidad (PageRank/degree)\nGrosor arista: fragmentos compartidos"
        self._draw_wrapped_text(draw, legend, x1 - 430, y0 + 22, 55, 24, body_font, (52, 68, 96), 3)

    def generate(self, project_name: str, theory_data: Dict[str, Any], template_key: str = "generic") -> BytesIO:
        width, height = 1200, 2200
        img = Image.new("RGB", (width, height), color=(245, 247, 250))
        draw = ImageDraw.Draw(img)

        title_font = self._font(44)
        subtitle_font = self._font(24)
        section_font = self._font(30)
        body_font = self._font(21)

        model = theory_data.get("model_json", {}) or {}
        validation = theory_data.get("validation", {}) or {}
        summary = validation.get("network_metrics_summary", {}) or {}
        counts = summary.get("counts", {}) or {}

        central = self._as_text(
            model.get("selected_central_category")
            or (model.get("central_phenomenon", {}) or {}).get("name")
            or "No disponible"
        )

        conditions = self._bullet_lines(model.get("conditions"), limit=3)
        actions = self._bullet_lines(model.get("actions"), limit=3)
        consequences = self._bullet_lines(model.get("consequences"), limit=3)
        propositions = self._bullet_lines(theory_data.get("propositions", []), limit=4)
        gaps = self._bullet_lines(theory_data.get("gaps", []), limit=4)

        draw.rectangle((0, 0, width, 180), fill=(15, 56, 96))
        draw.text((40, 46), f"TheoGen - {project_name}", fill=(255, 255, 255), font=title_font)
        draw.text((40, 116), f"Template: {template_key}", fill=(198, 228, 255), font=subtitle_font)

        draw.rounded_rectangle((40, 220, width - 40, 360), radius=24, fill=(232, 245, 255), outline=(63, 114, 175), width=3)
        draw.text((60, 248), "Categoria central", fill=(22, 62, 110), font=section_font)
        self._draw_wrapped_text(draw, central, 60, 296, 80, 30, body_font, (20, 40, 70), 2)

        card_w = (width - 120) // 2
        left_x = 40
        right_x = left_x + card_w + 40

        def draw_card(x: int, y: int, title: str, lines: List[str], fill=(255, 255, 255)) -> None:
            draw.rounded_rectangle((x, y, x + card_w, y + 250), radius=18, fill=fill, outline=(206, 216, 228), width=2)
            draw.text((x + 18, y + 16), title, fill=(31, 55, 86), font=section_font)
            yy = y + 62
            if not lines:
                lines = ["- Sin datos"]
            for line in lines[:5]:
                yy = self._draw_wrapped_text(draw, line, x + 20, yy, 40, 28, body_font, (60, 72, 88), 2)

        draw_card(left_x, 410, "Condiciones", conditions, fill=(255, 255, 255))
        draw_card(right_x, 410, "Acciones", actions, fill=(255, 255, 255))
        draw_card(left_x, 700, "Consecuencias", consequences, fill=(255, 255, 255))
        draw_card(right_x, 700, "Proposiciones", propositions, fill=(255, 255, 255))

        self._draw_network_panel(
            img,
            (40, 990, width - 40, 1450),
            central,
            summary,
            section_font,
            body_font,
        )

        draw.rounded_rectangle((40, 1490, width - 40, 1750), radius=20, fill=(255, 252, 243), outline=(235, 196, 122), width=2)
        draw.text((60, 1518), "Brechas y riesgos", fill=(118, 75, 0), font=section_font)
        yy = 1568
        for line in gaps if gaps else ["- Sin brechas identificadas"]:
            yy = self._draw_wrapped_text(draw, line, 60, yy, 90, 28, body_font, (98, 75, 40), 2)

        draw.rounded_rectangle((40, 1790, width - 40, 2150), radius=20, fill=(240, 245, 255), outline=(147, 172, 219), width=2)
        draw.text((60, 1818), "Metricas de calidad", fill=(37, 63, 104), font=section_font)
        metrics_lines = [
            f"- Confianza: {theory_data.get('confidence_score', 0)}",
            f"- Proposiciones: {len(theory_data.get('propositions', []) or [])}",
            f"- Brechas: {len(theory_data.get('gaps', []) or [])}",
            f"- Categorias (grafo): {counts.get('category_count', 0)}",
            f"- Codigos (grafo): {counts.get('code_count', 0)}",
            f"- Fragmentos (grafo): {counts.get('fragment_count', 0)}",
        ]
        yy = 1868
        for line in metrics_lines:
            yy = self._draw_wrapped_text(draw, line, 60, yy, 80, 30, body_font, (52, 68, 96), 2)

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

