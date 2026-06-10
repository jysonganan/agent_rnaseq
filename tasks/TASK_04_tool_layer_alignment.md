# TASK-04: Tool Layer — Alignment Tools (STAR, samtools)

## Goal
Implement deterministic tool wrappers for STAR alignment and samtools post-processing as specified in `docs/specs/tool_contracts.md`.

## Requirements
- Tool functions: `run_star_align`, `run_samtools_sort_index`.
- Support `alignment_mode`: genome, transcriptome, or both (two STAR passes).
- Parse STAR `Log.final.out` to produce `alignment_stats` dict.
- Parse `samtools flagstat` output to produce structured dict.
- Both tools must work in dry-run mode (no binary required) for unit tests.

## Files to Create
```
src/tools/alignment/
  __init__.py
  star.py              # run_star_align + STARAlignInput/Output
  samtools.py          # run_samtools_sort_index + SamtoolsInput/Output
  parsers.py           # STAR log parser, flagstat parser
tests/tools/
  test_star.py
  test_samtools.py
  fixtures/
    star_log_final.out
    samtools_flagstat.txt
```

## Files to Edit
- `src/tools/__init__.py` — export alignment tools.

## Acceptance Criteria
- [ ] `run_star_align` with mocked subprocess returns valid `STARAlignOutput`.
- [ ] STAR `Log.final.out` parser extracts: `uniquely_mapped_pct`, `multi_mapped_pct`, `total_reads`.
- [ ] `alignment_mode=both` triggers two STAR subprocess calls.
- [ ] `run_samtools_sort_index` returns `sorted_bam_path`, `bai_path`, and parsed `flagstat`.
- [ ] `STARAlignInput.extra_args` list is passed through to subprocess without modification.
- [ ] Invalid `threads` value (e.g., 0) rejected by Pydantic before subprocess call.
- [ ] Timeout is enforced and raises `ToolTimeoutError`.

## Definition of Done
`pytest tests/tools/test_star.py tests/tools/test_samtools.py` green.
