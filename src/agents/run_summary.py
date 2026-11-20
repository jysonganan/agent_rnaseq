"""Post-run summary for chat-originated runs (the orchestrator's stage-summary step).

Two parts, kept strictly separate:

* ``results_markdown`` — deterministic. Every number is copied from a validated tool
  output stored in ``RunState.stage_outputs``.
* ``narrative`` — one single-turn LLM completion over numbers-only excerpts of those
  outputs. The LLM is told not to state numbers, and any sentence containing a digit is
  dropped (``_strip_numeric_sentences``), so no LLM-generated number reaches the database.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.agents.run_events import output_excerpt
from src.agents.sanitize import sanitize_text

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DIGIT = re.compile(r"\d")


def _items(entry: dict, key: str) -> dict[str, dict]:
    return {k: (v or {}).get("output") or {} for k, v in (entry.get(key) or {}).items()}


def results_markdown(state: dict[str, Any], sample_names: dict[str, str] | None = None) -> str:
    """Deterministic Markdown results section built only from validated stage outputs."""
    names = sample_names or {}
    outs = state.get("stage_outputs") or {}
    lines = ["**Results**"]

    for stage in state.get("completed_stages") or []:
        entry = outs.get(stage) or {}
        out = entry.get("output") or {}
        if stage == "qc":
            per = _items(entry, "samples")
            fails = sum(
                1
                for o in per.values()
                for v in (o.get("summary") or {}).values()
                if str(v).upper() == "FAIL"
            )
            lines.append(f"- QC: {len(per)} sample(s); {fails} FastQC module FAIL flag(s)")
        elif stage == "alignment":
            per = _items(entry, "samples")
            rates = [
                f"{names.get(sid, sid[:8])} {o['alignment_stats']['uniquely_mapped_pct']}%"
                for sid, o in per.items()
                if "uniquely_mapped_pct" in (o.get("alignment_stats") or {})
            ]
            lines.append(
                f"- Alignment: {len(per)} sample(s)"
                + (f"; uniquely mapped: {', '.join(rates)}" if rates else "")
            )
        elif stage == "quantification":
            lines.append(f"- Quantification: {len(_items(entry, 'samples'))} sample(s)")
        elif stage == "variant_calling":
            per = _items(entry, "samples")
            counts = [
                f"{names.get(sid, sid[:8])} {o['pass_variant_count']}"
                for sid, o in per.items()
                if "pass_variant_count" in o
            ]
            lines.append(f"- Variant calling: PASS variants per sample: {', '.join(counts)}")
        elif stage == "splicing":
            for name, o in _items(entry, "contrasts").items():
                total = sum((o.get("significant_events_count") or {}).values())
                lines.append(f"- Splicing `{name}`: {total} significant event(s)")
        elif stage == "differential_expression":
            for name, c in (out.get("contrast_summaries") or {}).items():
                lines.append(
                    f"- DE `{name}`: {c['upregulated']} up, {c['downregulated']} down "
                    f"of {c['total_genes']} genes tested"
                )
        elif stage == "gsea":
            for name, c in (out.get("per_contrast") or {}).items():
                lines.append(
                    f"- GSEA `{name}`: {c['significant_pathway_count']} significant pathway(s)"
                )
        elif stage == "scrna_seq":
            for sid, o in _items(entry, "samples").items():
                n = (o.get("cluster_summary") or {}).get("n_clusters")
                lines.append(f"- scRNA-seq {names.get(sid, sid[:8])}: {n} cluster(s)")
        elif stage == "visualization":
            lines.append(
                "- Visualization: dashboard data"
                + (" and genome browser tracks" if out.get("bigwig_paths") else "")
                + " ready"
            )
        elif stage == "report":
            lines.append("- Report: HTML/Markdown report generated")

    if state.get("failed_stage"):
        lines.append(
            f"- **Stage `{state['failed_stage']}` failed:** "
            f"{sanitize_text(state.get('error_message') or '', 300)}"
        )
    return "\n".join(lines)


def _strip_numeric_sentences(text: str) -> str:
    kept = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s and not _DIGIT.search(s)]
    return " ".join(kept)


def narrative(llm: Any, model: str, state: dict[str, Any]) -> str:
    """Short qualitative interpretation; returns "" if the LLM fails or only gives numbers."""
    excerpts = {
        stage: output_excerpt(entry)
        for stage, entry in (state.get("stage_outputs") or {}).items()
        if stage in (state.get("completed_stages") or [])
    }
    payload = {
        "completed_stages": state.get("completed_stages") or [],
        "failed_stage": state.get("failed_stage"),
        "validated_output_excerpts": excerpts,
    }
    try:
        resp = llm.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarise a finished RNA-seq pipeline run for a scientist. You "
                        "receive validated outputs as JSON. Write two or three sentences of "
                        "qualitative interpretation and suggested next steps. Do NOT write any "
                        "numbers, percentages, counts or gene names — the exact results table "
                        "is shown separately. If a stage failed, suggest how to investigate."
                    ),
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
            max_tokens=200,
        )
        text = resp.choices[0].message.content or ""
    except Exception:
        return ""
    return sanitize_text(_strip_numeric_sentences(text), 1200)
