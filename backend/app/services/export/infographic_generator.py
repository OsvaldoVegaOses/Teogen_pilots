from __future__ import annotations

import textwrap
from io import BytesIO
from typing import Any, Dict, List

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

    def generate(self, project_name: str, theory_data: Dict[str, Any], template_key: str = "generic") -> BytesIO:
        width, height = 1200, 1800
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

        draw.rounded_rectangle((40, 990, width - 40, 1250), radius=20, fill=(255, 252, 243), outline=(235, 196, 122), width=2)
        draw.text((60, 1018), "Brechas y riesgos", fill=(118, 75, 0), font=section_font)
        yy = 1068
        for line in gaps if gaps else ["- Sin brechas identificadas"]:
            yy = self._draw_wrapped_text(draw, line, 60, yy, 90, 28, body_font, (98, 75, 40), 2)

        draw.rounded_rectangle((40, 1290, width - 40, 1730), radius=20, fill=(240, 245, 255), outline=(147, 172, 219), width=2)
        draw.text((60, 1318), "Metricas de calidad", fill=(37, 63, 104), font=section_font)
        metrics_lines = [
            f"- Confianza: {theory_data.get('confidence_score', 0)}",
            f"- Proposiciones: {len(theory_data.get('propositions', []) or [])}",
            f"- Brechas: {len(theory_data.get('gaps', []) or [])}",
            f"- Categorias (grafo): {counts.get('category_count', 0)}",
            f"- Codigos (grafo): {counts.get('code_count', 0)}",
            f"- Fragmentos (grafo): {counts.get('fragment_count', 0)}",
        ]
        yy = 1368
        for line in metrics_lines:
            yy = self._draw_wrapped_text(draw, line, 60, yy, 80, 30, body_font, (52, 68, 96), 2)

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
