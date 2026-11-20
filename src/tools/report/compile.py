"""Final analysis report (Markdown + HTML) assembled from validated tool outputs.

See ``docs/specs/tool_contracts.md`` §10. No LLM text and no recomputation: every number is
copied from a validated ``ToolOutput``; every interpolated value is HTML-escaped.
"""

from __future__ import annotations

import html
import os
from datetime import UTC, datetime
from string import Template
from typing import Any

from pydantic import BaseModel

from src.tools.base import ToolValidationError, tool_call

TOOL_VERSION = "report_compiler 1.0"


class ReportInput(BaseModel):
    run_id: str
    run_name: str
    qc_summary: dict | None = None
    de_summary: dict | None = None
    gsea_summary: dict | None = None
    artifact_paths: dict[str, str] = {}
    output_dir: str
    template_path: str


class ReportOutput(BaseModel):
    html_report_path: str
    markdown_report_path: str
    tool_version: str | None = None


Table = tuple[str, list[str], list[list[Any]]]


def _qc_table(qc: dict) -> Table:
    rows = []
    for sample, out in sorted(qc.items()):
        statuses = list(((out or {}).get("summary") or {}).values())
        rows.append(
            [
                sample,
                *(
                    sum(1 for s in statuses if str(s).upper() == k)
                    for k in ("PASS", "WARN", "FAIL")
                ),
            ]
        )
    return "Quality control (FastQC modules)", ["Sample", "PASS", "WARN", "FAIL"], rows


def _de_table(de: dict) -> Table:
    cols = ["total_genes", "upregulated", "downregulated", "not_significant"]
    rows = [[c, *((s or {}).get(k, "") for k in cols)] for c, s in sorted(de.items())]
    return (
        "Differential expression (DESeq2)",
        ["Contrast", "Genes tested", "Up", "Down", "Not significant"],
        rows,
    )


def _gsea_table(gsea: dict) -> Table:
    rows = [[c, (s or {}).get("significant_pathway_count", "")] for c, s in sorted(gsea.items())]
    return "Pathway enrichment (Reactome GSEA)", ["Contrast", "Significant pathways"], rows


def _md_table(title: str, header: list[str], rows: list[list[Any]]) -> str:
    lines = [f"## {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def _html_table(title: str, header: list[str], rows: list[list[Any]]) -> str:
    esc = html.escape
    head = "".join(f"<th>{esc(str(h))}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{esc(str(v))}</td>" for v in r) + "</tr>" for r in rows)
    return f"<h2>{esc(title)}</h2>\n<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>\n"


@tool_call
def compile_report(inp: ReportInput) -> ReportOutput:
    if not os.path.isfile(inp.template_path):
        raise ToolValidationError("compile_report", "template_path", "template not found")
    with open(inp.template_path) as fh:
        template = Template(fh.read())

    tables: list[Table] = []
    if inp.qc_summary:
        tables.append(_qc_table(inp.qc_summary))
    if inp.de_summary:
        tables.append(_de_table(inp.de_summary))
    if inp.gsea_summary:
        tables.append(_gsea_table(inp.gsea_summary))
    artifacts = [
        [label, os.path.basename(path)] for label, path in sorted(inp.artifact_paths.items())
    ]
    if artifacts:
        tables.append(("Artifacts", ["Artifact", "File"], artifacts))

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    title = f"RNA-seq report: {inp.run_name}"
    meta = f"Run `{inp.run_id}` — generated {generated}"

    md = "\n".join([f"# {title}", "", meta, "", *(_md_table(*t) for t in tables)])
    if not tables:
        md += "\nNo results were available for this run.\n"

    body = f"<p>{html.escape(meta.replace('`', ''))}</p>\n" + "".join(
        _html_table(*t) for t in tables
    )
    if not tables:
        body += "<p>No results were available for this run.</p>\n"
    rendered = template.safe_substitute(title=html.escape(title), body=body)

    os.makedirs(inp.output_dir, exist_ok=True)
    md_path = os.path.join(inp.output_dir, "report.md")
    html_path = os.path.join(inp.output_dir, "report.html")
    with open(md_path, "w") as fh:
        fh.write(md)
    with open(html_path, "w") as fh:
        fh.write(rendered)
    return ReportOutput(
        html_report_path=html_path, markdown_report_path=md_path, tool_version=TOOL_VERSION
    )
