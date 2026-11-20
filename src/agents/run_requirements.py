"""Deterministic checks for the analysis inputs only the user can decide.

Which conditions to compare (and in which direction) and the sequencing read length
change the scientific result, so the system never guesses them. This module is the
single source of truth used by:

* ``POST /runs``            → 422 with :func:`format_issues`
* chat ``dispatch_from_chat`` → follow-up question from :func:`clarification_question`
* ``OrchestratorAgent.execute_run`` → refuses to start an under-specified run

No LLM is involved here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from src.schemas.run import DEContrast

CONTRAST_STAGES: frozenset[str] = frozenset({"differential_expression", "splicing"})
READ_LENGTH_STAGES: frozenset[str] = frozenset({"splicing"})

IssueCode = Literal[
    "missing_contrasts",
    "unknown_condition",
    "empty_group",
    "duplicate_contrast",
    "missing_condition",
    "no_replicates",
    "missing_read_length",
]


@dataclass(frozen=True)
class SampleFacts:
    sample_id: str
    name: str
    condition: str | None
    read_length: int | None = None


@dataclass(frozen=True)
class InputIssue:
    code: IssueCode
    message: str


def sample_facts(samples: Iterable[Any]) -> list[SampleFacts]:
    """Build :class:`SampleFacts` from ``Sample`` ORM rows (or anything shaped like them)."""
    facts = []
    for s in samples:
        meta = getattr(s, "sample_metadata", None) or {}
        rl = meta.get("read_length")
        facts.append(
            SampleFacts(
                sample_id=str(s.id),
                name=s.name,
                condition=(s.condition or "").strip() or None,
                read_length=int(rl) if isinstance(rl, int | str) and str(rl).isdigit() else None,
            )
        )
    return facts


def condition_counts(samples: Sequence[SampleFacts]) -> dict[str, int]:
    counts = Counter(s.condition for s in samples if s.condition)
    return dict(sorted(counts.items()))


def _describe_conditions(samples: Sequence[SampleFacts]) -> str:
    counts = condition_counts(samples)
    if not counts:
        return "none of the selected samples has a condition"
    return ", ".join(f"{c} ({n} sample{'s' if n != 1 else ''})" for c, n in counts.items())


def resolve_read_length(read_length: int | None, samples: Sequence[SampleFacts]) -> int | None:
    """User-given read length, else the one value shared by every sample's metadata."""
    if read_length is not None:
        return read_length
    lengths = {s.read_length for s in samples}
    if len(lengths) == 1:
        return lengths.pop()
    return None


def check_analysis_inputs(
    stages: Iterable[str],
    samples: Sequence[SampleFacts],
    contrasts: Sequence[DEContrast],
    read_length: int | None,
) -> list[InputIssue]:
    """Return every problem with the user-decided inputs (empty list = OK)."""
    stage_set = {str(s) for s in stages}
    issues: list[InputIssue] = []

    if stage_set & CONTRAST_STAGES:
        unlabeled = [s.name for s in samples if not s.condition]
        if unlabeled:
            issues.append(
                InputIssue(
                    "missing_condition",
                    "These samples have no condition, so they cannot be placed in a "
                    f"comparison: {', '.join(sorted(unlabeled))}.",
                )
            )

        counts = condition_counts(samples)
        if not contrasts:
            issues.append(
                InputIssue(
                    "missing_contrasts",
                    "Differential expression/splicing needs at least one contrast. "
                    f"Available conditions: {_describe_conditions(samples)}.",
                )
            )

        seen_names: set[str] = set()
        seen_pairs: set[tuple[str, str]] = set()
        for c in contrasts:
            for side in (c.numerator, c.denominator):
                if side not in counts:
                    issues.append(
                        InputIssue(
                            "unknown_condition",
                            f"Contrast '{c.name}' uses condition '{side}', which no selected "
                            f"sample has. Available conditions: {_describe_conditions(samples)}.",
                        )
                    )
            pair = (c.numerator, c.denominator)
            if c.name in seen_names or pair in seen_pairs:
                issues.append(
                    InputIssue("duplicate_contrast", f"Contrast '{c.name}' is listed twice.")
                )
            seen_names.add(c.name or "")
            seen_pairs.add(pair)

        if contrasts and counts and len(samples) <= len(counts):
            issues.append(
                InputIssue(
                    "no_replicates",
                    "DESeq2 needs at least one condition with two or more samples "
                    f"(selected: {_describe_conditions(samples)}).",
                )
            )

    if stage_set & READ_LENGTH_STAGES and resolve_read_length(read_length, samples) is None:
        issues.append(
            InputIssue(
                "missing_read_length",
                "Splicing analysis (rMATS) needs the sequencing read length in bp.",
            )
        )

    return issues


def format_issues(issues: Sequence[InputIssue]) -> str:
    return " ".join(i.message for i in issues)


def clarification_question(issues: Sequence[InputIssue], samples: Sequence[SampleFacts]) -> str:
    """Deterministic follow-up question for the chat UI (Markdown)."""
    codes = {i.code for i in issues}
    parts: list[str] = []

    if codes & {"missing_contrasts", "unknown_condition", "duplicate_contrast"}:
        conds = list(condition_counts(samples))
        lines = [
            "Which conditions should I compare? The selected samples have these conditions:",
            "",
            *(
                f"- **{c}** ({n} sample{'s' if n != 1 else ''})"
                for c, n in condition_counts(samples).items()
            ),
            "",
            "Please list each comparison as `<test> vs <reference>` — fold changes are "
            "reported as test relative to reference. You can give several.",
        ]
        if len(conds) >= 2:
            ref = conds[0]
            examples = [f"`{c} vs {ref}`" for c in conds[1:3]]
            lines.append(f"For example: {', '.join(examples)}.")
        problems = [
            i.message for i in issues if i.code in ("unknown_condition", "duplicate_contrast")
        ]
        if problems:
            lines += ["", "Note: " + " ".join(problems)]
        parts.append("\n".join(lines))

    for code in ("missing_condition", "no_replicates"):
        parts.extend(i.message for i in issues if i.code == code)

    if "missing_read_length" in codes:
        parts.append(
            "Splicing analysis (rMATS) needs the sequencing read length. "
            "What read length (in bp, e.g. 100 or 150) were these samples sequenced with?"
        )

    return "\n\n".join(parts)
