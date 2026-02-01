"""Report generator: pipeline payload -> HTML (always) and PDF (when WeasyPrint
with its system libraries is available — the worker container has them)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)


def render_html(payload: dict) -> str:
    template = _env.get_template("report.html.j2")
    return template.render(**payload)


def render_pdf(html: str) -> bytes | None:
    """Return PDF bytes, or None when WeasyPrint isn't usable in this runtime."""
    try:
        from weasyprint import HTML  # noqa: PLC0415 — heavy optional dependency
    except Exception:
        return None
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None
