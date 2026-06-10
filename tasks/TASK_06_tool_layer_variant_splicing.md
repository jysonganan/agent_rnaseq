# TASK-06: Tool Layer — Variant Calling & Splicing (GATK, rMATS)

## Goal
Implement tool wrappers for GATK HaplotypeCaller, GATK VariantFilter, and rMATS splicing analysis.

## Requirements
- Tool functions: `run_gatk_haplotypecaller`, `run_gatk_variant_filter`, `run_rmats`.
- VCF output parsers: count PASS variants, count filtered variants.
- rMATS output parser: count significant events per event type (SE, A5SS, A3SS, MXE, RI).
- Dry-run mode for all three tools.

## Files to Create
```
src/tools/variant/
  __init__.py
  gatk.py              # run_gatk_haplotypecaller, run_gatk_variant_filter + Input/Output models
  parsers.py           # VCF PASS/FILTER count parser
src/tools/splicing/
  __init__.py
  rmats.py             # run_rmats + RMATSInput/Output
  parsers.py           # rMATS summary parser
tests/tools/
  test_gatk.py
  test_rmats.py
  fixtures/
    sample.vcf
    rmats_summary.txt
    rmats_SE.MATS.JC.txt
```

## Files to Edit
- `src/tools/__init__.py` — export variant and splicing tools.

## Acceptance Criteria
- [ ] `run_gatk_haplotypecaller` passes interval list and dbSNP args to subprocess when provided.
- [ ] `run_gatk_variant_filter` correctly counts PASS and FILTERED variants from fixture VCF.
- [ ] `run_rmats` with mocked subprocess returns correct `significant_events_count` per event type.
- [ ] `GATKHaplotypeCallerOutput.variant_count` is an integer, not a string.
- [ ] Non-zero exit on any GATK command raises `ToolExecutionError`.
- [ ] `RMATSInput.bam_list_b1` must have at least 1 entry; validated by Pydantic.

## Definition of Done
`pytest tests/tools/test_gatk.py tests/tools/test_rmats.py` green.
