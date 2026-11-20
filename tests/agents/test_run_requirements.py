"""Tests for the deterministic user-input checks and follow-up questions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.run_requirements import (
    SampleFacts,
    check_analysis_inputs,
    clarification_question,
)
from src.schemas.run import DEContrast

DE = ["alignment", "quantification", "differential_expression"]


def _samples(*conds: str | None, read_length: int | None = None) -> list[SampleFacts]:
    return [SampleFacts(f"id{i}", f"S{i}", c, read_length) for i, c in enumerate(conds)]


def _codes(issues) -> set[str]:  # type: ignore[no-untyped-def]
    return {i.code for i in issues}


class TestDEContrast:
    def test_default_name(self) -> None:
        assert DEContrast(numerator="KO 1", denominator="WT").name == "KO_1_vs_WT"

    def test_self_comparison_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DEContrast(numerator="a", denominator="a")

    def test_unsafe_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DEContrast(name="../x", numerator="a", denominator="b")


class TestCheckAnalysisInputs:
    def test_no_de_stage_needs_nothing(self) -> None:
        assert check_analysis_inputs(["qc"], _samples(None), [], None) == []

    def test_missing_contrasts(self) -> None:
        issues = check_analysis_inputs(DE, _samples("a", "a", "b"), [], None)
        assert _codes(issues) == {"missing_contrasts"}

    def test_many_conditions_and_contrasts_ok(self) -> None:
        contrasts = [
            DEContrast(numerator="b", denominator="a"),
            DEContrast(numerator="c", denominator="a"),
            DEContrast(numerator="b", denominator="c"),
        ]
        samples = _samples("a", "a", "b", "b", "c", "c", "d")
        assert check_analysis_inputs(DE, samples, contrasts, None) == []

    def test_unknown_condition(self) -> None:
        issues = check_analysis_inputs(
            DE, _samples("a", "a", "b"), [DEContrast(numerator="z", denominator="a")], None
        )
        assert _codes(issues) == {"unknown_condition"}

    def test_duplicate_contrast(self) -> None:
        c = DEContrast(numerator="b", denominator="a")
        issues = check_analysis_inputs(DE, _samples("a", "a", "b"), [c, c], None)
        assert _codes(issues) == {"duplicate_contrast"}

    def test_unlabelled_sample(self) -> None:
        c = DEContrast(numerator="b", denominator="a")
        issues = check_analysis_inputs(DE, _samples("a", "a", "b", None), [c], None)
        assert "missing_condition" in _codes(issues)

    def test_no_replicates(self) -> None:
        c = DEContrast(numerator="b", denominator="a")
        issues = check_analysis_inputs(DE, _samples("a", "b"), [c], None)
        assert _codes(issues) == {"no_replicates"}

    def test_splicing_read_length_from_user_or_metadata(self) -> None:
        c = [DEContrast(numerator="b", denominator="a")]
        stages = ["alignment", "splicing"]
        samples = _samples("a", "a", "b")
        assert _codes(check_analysis_inputs(stages, samples, c, None)) == {"missing_read_length"}
        assert check_analysis_inputs(stages, samples, c, 100) == []
        assert check_analysis_inputs(stages, _samples("a", "a", "b", read_length=75), c, None) == []


class TestClarificationQuestion:
    def test_lists_conditions_and_format(self) -> None:
        samples = _samples("ctrl", "ctrl", "drugA", "drugB")
        q = clarification_question(check_analysis_inputs(DE, samples, [], None), samples)
        assert "**ctrl** (2 samples)" in q
        assert "**drugA** (1 sample)" in q
        assert "`<test> vs <reference>`" in q
        assert "`drugA vs ctrl`" in q

    def test_asks_read_length(self) -> None:
        samples = _samples("a", "a", "b")
        issues = check_analysis_inputs(["alignment", "splicing"], samples, [], None)
        q = clarification_question(issues, samples)
        assert "Which conditions" in q and "read length" in q
