# TASK-07: Tool Layer — DESeq2 & Reactome GSEA (R Subprocess Tools)

## Goal
Implement Python tool wrappers that invoke validated R scripts for differential expression (DESeq2) and pathway enrichment (Reactome/fgsea), and parse their outputs into typed Pydantic models.

## Requirements
- Tool functions: `run_deseq2`, `run_reactome_gsea`.
- Validated R scripts (not LLM-generated): `src/r/deseq2_analysis.R`, `src/r/reactome_gsea.R`.
- Python parsers for DESeq2 result CSV and GSEA result CSV.
- R scripts called via `subprocess.run(["Rscript", script_path, ...])`.
- R script arguments passed as positional CLI args (never string interpolation into R code).
- Output CSV schemas validated against Pydantic before storage.

## Files to Create
```
src/tools/de/
  __init__.py
  deseq2.py            # run_deseq2 + DESeq2Input/Output + DEContrast
  parsers.py           # DESeq2 CSV parser → list[DEGResult]
src/tools/gsea/
  __init__.py
  reactome.py          # run_reactome_gsea + ReactomeGSEAInput/Output
  parsers.py           # Reactome CSV parser → list[GSEAResult]
src/r/
  deseq2_analysis.R    # Validated R script: args = counts_path, metadata_path, contrast, output_dir
  reactome_gsea.R      # Validated R script: args = de_results_path, organism, output_dir
tests/tools/
  test_deseq2.py
  test_reactome_gsea.py
  fixtures/
    deseq2_results.csv
    gsea_results.csv
    counts_matrix.csv
    sample_metadata.csv
```

## Files to Edit
- `src/tools/__init__.py` — export DE and GSEA tools.
- `pyproject.toml` — document R >= 4.0 as external dependency.

## Acceptance Criteria
- [ ] `run_deseq2` with mocked Rscript subprocess returns `DESeq2Output` with correct contrast summaries.
- [ ] DESeq2 CSV parser correctly populates `DEContrastSummary` (upregulated, downregulated counts) from fixture.
- [ ] `run_reactome_gsea` returns `significant_pathway_count` matching fixture.
- [ ] R scripts do not accept free-text R code as input (no `eval()` patterns).
- [ ] R script args are passed as positional CLI arguments to `Rscript`, not embedded in R code strings.
- [ ] `DESeq2Input.alpha` rejects values outside 0.001–0.1 range.
- [ ] `DESeq2Input.contrasts` must have at least 1 contrast; validated by Pydantic.
- [ ] LLM summary of DE results is generated from parsed `DEContrastSummary`, never from raw CSV content.

## Definition of Done
`pytest tests/tools/test_deseq2.py tests/tools/test_reactome_gsea.py` green.
R scripts pass `Rscript --vanilla src/r/deseq2_analysis.R --help` without error.
