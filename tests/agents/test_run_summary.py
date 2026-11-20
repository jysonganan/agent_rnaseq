"""Tests for the post-run summary (deterministic results + numbers-free LLM narrative)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.agents.run_summary import _strip_numeric_sentences, narrative, results_markdown

STATE = {
    "completed_stages": ["qc", "alignment", "differential_expression", "gsea"],
    "failed_stage": None,
    "error_message": None,
    "stage_outputs": {
        "qc": {"samples": {"s1": {"output": {"summary": {"a": "PASS", "b": "FAIL"}}}}},
        "alignment": {
            "samples": {"s1": {"output": {"alignment_stats": {"uniquely_mapped_pct": 91.5}}}}
        },
        "differential_expression": {
            "output": {
                "contrast_summaries": {
                    "B_vs_A": {
                        "total_genes": 100,
                        "upregulated": 7,
                        "downregulated": 3,
                        "not_significant": 90,
                    }
                }
            }
        },
        "gsea": {"output": {"per_contrast": {"B_vs_A": {"significant_pathway_count": 4}}}},
    },
}


def _llm(text: str) -> MagicMock:
    client = MagicMock()
    msg = SimpleNamespace(content=text)
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)]
    )
    return client


def test_results_copied_from_validated_outputs() -> None:
    md = results_markdown(STATE, {"s1": "ctrl_1"})
    assert "- QC: 1 sample(s); 1 FastQC module FAIL flag(s)" in md
    assert "ctrl_1 91.5%" in md
    assert "- DE `B_vs_A`: 7 up, 3 down of 100 genes tested" in md
    assert "- GSEA `B_vs_A`: 4 significant pathway(s)" in md


def test_failed_stage_reported_without_paths() -> None:
    state = {**STATE, "failed_stage": "gsea", "error_message": "boom at /data/x/y.csv"}
    md = results_markdown(state)
    assert "Stage `gsea` failed" in md and "/data/x" not in md


def test_numeric_sentences_dropped() -> None:
    text = "Expression changed strongly. About 120 genes went up! Pathways look coherent."
    assert _strip_numeric_sentences(text) == "Expression changed strongly. Pathways look coherent."


def test_narrative_gets_only_numeric_excerpts_and_is_filtered() -> None:
    llm = _llm("Treatment has a clear effect. It changed 7 genes.")
    text = narrative(llm, "gpt-4o", STATE)
    assert text == "Treatment has a clear effect."
    sent = llm.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "B_vs_A" in sent and "/" not in sent  # excerpts carry no paths


def test_narrative_failure_returns_empty() -> None:
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("api down")
    assert narrative(llm, "gpt-4o", STATE) == ""
