"""Streamlit data preparation — collects validated result files into the dashboard format.

See ``docs/specs/tool_contracts.md`` §9. Values are copied verbatim; nothing is recomputed.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from pydantic import BaseModel

from src.tools.base import ToolValidationError, tool_call

TOOL_VERSION = "streamlit_prep 1.0"

_DE_REQUIRED = {"gene_id", "log2FoldChange", "padj"}
_GSEA_REQUIRED = {"pathway_id", "pathway_name", "NES", "padj"}


class StreamlitDataPrepInput(BaseModel):
    run_id: str
    de_results_dir: str | None = None
    gsea_results_dir: str | None = None
    qc_metrics_path: str | None = None
    output_dir: str


class StreamlitDataPrepOutput(BaseModel):
    output_dir: str
    manifest_path: str
    tool_version: str | None = None


def _merge_with_contrast(
    files: list[tuple[str, Path]], required: set[str], out_path: Path, label: str
) -> bool:
    """Concatenate CSVs, prepending a ``contrast`` column. Returns False if no files."""
    if not files:
        return False
    header: list[str] | None = None
    with open(out_path, "w", newline="") as out_fh:
        writer = csv.writer(out_fh)
        for contrast, path in files:
            with open(path, newline="") as fh:
                reader = csv.reader(fh)
                cols = next(reader, None) or []
                missing = required - set(cols)
                if missing:
                    raise ToolValidationError(
                        "prepare_streamlit_data",
                        label,
                        f"{path.name} lacks columns {sorted(missing)}",
                    )
                if header is None:
                    header = cols
                    writer.writerow(["contrast", *header])
                elif cols != header:
                    raise ToolValidationError(
                        "prepare_streamlit_data", label, f"{path.name} has a different header"
                    )
                for row in reader:
                    writer.writerow([contrast, *row])
    return True


def _de_files(de_dir: str) -> list[tuple[str, Path]]:
    return [
        (p.name[: -len("_results.csv")], p)
        for p in sorted(Path(de_dir).glob("*_results.csv"))
        if p.is_file()
    ]


def _gsea_files(gsea_dir: str) -> list[tuple[str, Path]]:
    return [
        (p.parent.name, p) for p in sorted(Path(gsea_dir).glob("*/gsea_results.csv")) if p.is_file()
    ]


@tool_call
def prepare_streamlit_data(inp: StreamlitDataPrepInput) -> StreamlitDataPrepOutput:
    out_dir = Path(inp.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    available: dict[str, str] = {}

    if (
        inp.de_results_dir
        and os.path.isdir(inp.de_results_dir)
        and _merge_with_contrast(
            _de_files(inp.de_results_dir),
            _DE_REQUIRED,
            out_dir / "de_results.csv",
            "de_results_dir",
        )
    ):
        available["de_results"] = "de_results.csv"

    if (
        inp.gsea_results_dir
        and os.path.isdir(inp.gsea_results_dir)
        and _merge_with_contrast(
            _gsea_files(inp.gsea_results_dir),
            _GSEA_REQUIRED,
            out_dir / "gsea_results.csv",
            "gsea_results_dir",
        )
    ):
        available["gsea_results"] = "gsea_results.csv"

    if inp.qc_metrics_path and os.path.isfile(inp.qc_metrics_path):
        with open(inp.qc_metrics_path) as fh:
            metrics = json.load(fh)
        if not isinstance(metrics, dict) or not isinstance(metrics.get("samples"), list):
            raise ToolValidationError(
                "prepare_streamlit_data", "qc_metrics_path", "expected {'samples': [...]}"
            )
        with open(out_dir / "qc_metrics.json", "w") as fh:
            json.dump(metrics, fh, indent=2)
        available["qc_metrics"] = "qc_metrics.json"

    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w") as fh:
        json.dump({"run_id": inp.run_id, "available": available}, fh, indent=2)

    return StreamlitDataPrepOutput(
        output_dir=str(out_dir), manifest_path=str(manifest_path), tool_version=TOOL_VERSION
    )
