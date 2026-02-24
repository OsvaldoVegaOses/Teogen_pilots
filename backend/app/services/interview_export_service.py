from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List


class InterviewExportService:
    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        if isinstance(value, list):
            return " | ".join([InterviewExportService._as_text(v) for v in value if v is not None])
        if isinstance(value, dict):
            preferred = [
                value.get("text"),
                value.get("name"),
                value.get("label"),
                value.get("definition"),
                value.get("id"),
            ]
            for item in preferred:
                if item:
                    return str(item)
            return str(value)
        return str(value)

    def generate_txt(self, project_name: str, interviews: List[Dict[str, Any]]) -> bytes:
        lines: List[str] = [f"Proyecto: {project_name}", ""]
        for i, interview in enumerate(interviews, 1):
            lines.append(f"=== Entrevista {i} ===")
            lines.append(f"ID: {interview.get('id')}")
            lines.append(f"Pseudonimo: {interview.get('participant_pseudonym') or ''}")
            lines.append(f"Metodo: {interview.get('transcription_method') or ''}")
            lines.append(f"Idioma: {interview.get('language') or ''}")
            lines.append("")
            for seg in interview.get("segments", []):
                spk = seg.get("speaker_id") or "N/A"
                ts = seg.get("time_range") or ""
                codes = seg.get("codes") or []
                codes_txt = f" [codes: {', '.join(codes)}]" if codes else ""
                lines.append(f"[{spk}] {ts} {seg.get('text', '')}{codes_txt}".strip())
            lines.append("")
        return "\n".join(lines).encode("utf-8")

    def generate_json(self, project_name: str, interviews: List[Dict[str, Any]]) -> bytes:
        import json

        payload = {"project": project_name, "interviews": interviews}
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def generate_pdf(self, project_name: str, interviews: List[Dict[str, Any]]) -> bytes:
        try:
            from reportlab.lib.pagesizes import LETTER
            from reportlab.pdfgen import canvas
        except Exception as e:
            raise RuntimeError(f"PDF export dependency missing: {e}") from e

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=LETTER)
        width, height = LETTER
        margin = 40
        y = height - margin

        def write_line(text: str, size: int = 10):
            nonlocal y
            c.setFont("Helvetica", size)
            c.drawString(margin, y, (text or "")[:160])
            y -= 14
            if y < margin:
                c.showPage()
                y = height - margin

        write_line(f"Proyecto: {project_name}", size=13)
        write_line("")
        for i, interview in enumerate(interviews, 1):
            write_line(f"Entrevista {i}: {interview.get('participant_pseudonym') or interview.get('id')}", size=11)
            write_line(f"Metodo: {interview.get('transcription_method') or ''} | Idioma: {interview.get('language') or ''}")
            for seg in interview.get("segments", []):
                spk = seg.get("speaker_id") or "N/A"
                ts = seg.get("time_range") or ""
                codes = seg.get("codes") or []
                codes_txt = f" [codes: {', '.join(codes)}]" if codes else ""
                write_line(f"[{spk}] {ts} {seg.get('text', '')}{codes_txt}")
            write_line("")

        c.save()
        buf.seek(0)
        return buf.getvalue()

    def generate_xlsx(self, project_name: str, interviews: List[Dict[str, Any]]) -> bytes:
        try:
            from openpyxl import Workbook
        except Exception as e:
            raise RuntimeError(f"XLSX export dependency missing: {e}") from e

        wb = Workbook()
        ws_summary = wb.active
        ws_summary.title = "Resumen"
        ws_summary.append(["Proyecto", project_name])
        ws_summary.append(["Entrevistas", len(interviews)])

        ws_segments = wb.create_sheet("Segmentos")
        ws_segments.append(
            [
                "interview_id",
                "participant_pseudonym",
                "fragment_id",
                "paragraph_index",
                "speaker_id",
                "start_ms",
                "end_ms",
                "text",
                "codes",
            ]
        )
        for interview in interviews:
            for seg in interview.get("segments", []):
                ws_segments.append(
                    [
                        interview.get("id"),
                        interview.get("participant_pseudonym"),
                        seg.get("fragment_id"),
                        seg.get("paragraph_index"),
                        seg.get("speaker_id"),
                        seg.get("start_ms"),
                        seg.get("end_ms"),
                        seg.get("text"),
                        ", ".join(seg.get("codes") or []),
                    ]
                )

        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    val = "" if cell.value is None else str(cell.value)
                    max_len = max(max_len, len(val))
                ws.column_dimensions[col_letter].width = min(80, max(12, max_len + 2))

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

    def generate(self, *, fmt: str, project_name: str, interviews: List[Dict[str, Any]]) -> tuple[bytes, str, str]:
        f = (fmt or "pdf").lower()
        if f == "txt":
            return self.generate_txt(project_name, interviews), "txt", "text/plain"
        if f == "json":
            return self.generate_json(project_name, interviews), "json", "application/json"
        if f == "pdf":
            return self.generate_pdf(project_name, interviews), "pdf", "application/pdf"
        if f == "xlsx":
            return (
                self.generate_xlsx(project_name, interviews),
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        raise ValueError(f"Unsupported interview export format: {fmt}")


interview_export_service = InterviewExportService()
