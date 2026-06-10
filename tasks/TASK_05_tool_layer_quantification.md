# TASK-05: Tool Layer — Quantification Tools (HTSeq, Salmon, RSEM)

## Goal
Implement deterministic tool wrappers for read quantification tools as specified in `docs/specs/tool_contracts.md`.

## Requirements
- Tool functions: `run_htseq_count`, `run_salmon_quant`, `run_rsem`.
- HTSeq output parser: TSV → dict with counts and summary statistics.
- Salmon output parser: `quant.sf` and `meta_info.json` → typed output.
- RSEM output parser: `*.genes.results` and `*.isoforms.results` paths.
- All three tools support dry-run mode for unit testing.

## Files to Create
```
src/tools/quantification/
  __init__.py
  htseq.py             # run_htseq_count + HTSeqInput/Output
  salmon.py            # run_salmon_quant + SalmonQuantInput/Output
  rsem.py              # run_rsem + RSEMInput/Output
  parsers.py           # HTSeq TSV parser, Salmon quant.sf parser, meta_info parser
tests/tools/
  test_htseq.py
  test_salmon.py
  test_rsem.py
  fixtures/
    htseq_counts.tsv
    salmon_quant.sf
    salmon_meta_info.json
    rsem_genes.results
```

## Files to Edit
- `src/tools/__init__.py` — export quantification tools.

## Acceptance Criteria
- [ ] `run_htseq_count` parses fixture TSV and returns correct `counted_reads`, `no_feature_reads`.
- [ ] `run_salmon_quant` returns `mapping_rate` and `inferred_lib_type` from fixture `meta_info.json`.
- [ ] `run_rsem` returns correct `genes_results_path` and `isoforms_results_path`.
- [ ] All three tools raise `ToolExecutionError` on non-zero subprocess exit.
- [ ] `HTSeqInput.stranded` only accepts `yes`, `no`, `reverse`; other values rejected.
- [ ] Unit tests cover single-end and paired-end inputs for Salmon.

## Definition of Done
`pytest tests/tools/test_htseq.py tests/tools/test_salmon.py tests/tools/test_rsem.py` green.
