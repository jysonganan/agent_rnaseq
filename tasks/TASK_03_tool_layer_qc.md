# TASK-03: Tool Layer — QC Tools (FastQC, MultiQC, RSeQC)

## Goal
Implement deterministic tool wrappers for the QC phase as specified in `docs/specs/tool_contracts.md`. Tools must be independently testable with mock subprocess calls.

## Requirements
- Tool functions: `run_fastqc`, `run_multiqc`, `run_rseqc`.
- Pydantic Input/Output models for each tool.
- `ToolExecutionError`, `ToolValidationError`, `ToolTimeoutError` exception types.
- Output parsers for FastQC summary ZIP, MultiQC JSON data, RSeQC text output.
- Tool version detection (call `fastqc --version` etc.) captured and returned.
- `@tool_call` decorator that: validates input, invokes tool, validates output, records timing.

## Files to Create
```
src/tools/
  __init__.py
  base.py              # ToolExecutionError, ToolValidationError, ToolTimeoutError, @tool_call decorator
  qc/
    __init__.py
    fastqc.py          # run_fastqc + FastQCInput/Output
    multiqc.py         # run_multiqc + MultiQCInput/Output
    rseqc.py           # run_rseqc + RSeQCInput/Output
    parsers.py         # FastQC zip parser, MultiQC JSON parser, RSeQC text parsers
tests/
  tools/
    __init__.py
    test_fastqc.py
    test_multiqc.py
    test_rseqc.py
    fixtures/
      fastqc_summary.txt
      multiqc_data.json
      rseqc_read_distribution.txt
```

## Files to Edit
- `pyproject.toml` — no new dependencies expected (subprocess only).

## Acceptance Criteria
- [ ] `run_fastqc(FastQCInput(...))` with mock subprocess returns valid `FastQCOutput`.
- [ ] `FastQCOutput.summary` correctly parsed from fixture `fastqc_summary.txt`.
- [ ] Invalid `FastQCInput` (e.g., empty `fastq_paths`) raises `ToolValidationError` before subprocess call.
- [ ] Non-zero subprocess exit raises `ToolExecutionError` with `exit_code` and `stderr` populated.
- [ ] `run_multiqc` parsed metrics match values in `multiqc_data.json` fixture.
- [ ] `run_rseqc` read_distribution result matches fixture.
- [ ] `@tool_call` decorator records elapsed time.
- [ ] 100% branch coverage on all parser functions.

## Definition of Done
`pytest tests/tools/` green. No subprocess calls made during tests (all mocked).
