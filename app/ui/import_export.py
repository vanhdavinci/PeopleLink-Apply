"""Backward-compatible aliases — UI đã gom vào app.ui.candidates."""
from app.ui.candidates import render_candidates_workspace as render_import_export_section

__all__ = ["render_import_export_section"]
