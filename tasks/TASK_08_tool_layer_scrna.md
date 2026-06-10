# TASK-08: Tool Layer — Single-Cell Tools (CellRanger, Scanpy)

## Goal
Implement tool wrappers for CellRanger count and Scanpy single-cell preprocessing pipeline, plus a small example scRNA-seq dataset and walkthrough notebook.

## Requirements
- Tool functions: `run_cellranger_count`, `run_scanpy_pipeline`.
- CellRanger output parser: `web_summary.csv` → `summary_stats` dict.
- Scanpy Python script (`src/scripts/scanpy_pipeline.py`) with hardened CLI interface (argparse).
- Example scRNA-seq dataset: PBMC 3k (public 10x dataset, ~30MB) or pointer to download script.
- Jupyter notebook walkthrough in `examples/scrnaseq/`.

## Files to Create
```
src/tools/scrna/
  __init__.py
  cellranger.py        # run_cellranger_count + CellRangerCountInput/Output
  scanpy_tool.py       # run_scanpy_pipeline + ScanpyInput/Output
  parsers.py           # CellRanger web_summary parser
src/scripts/
  scanpy_pipeline.py   # argparse CLI: --matrix-dir, --output-dir, --min-genes, etc.
examples/scrnaseq/
  README.md            # Setup instructions and dataset download
  download_pbmc3k.sh   # wget/curl script to download public PBMC 3k dataset
  analysis.ipynb       # End-to-end scRNA-seq walkthrough notebook
tests/tools/
  test_cellranger.py
  test_scanpy.py
  fixtures/
    cellranger_web_summary.csv
```

## Files to Edit
- `src/tools/__init__.py` — export scRNA tools.
- `pyproject.toml` — add scanpy, anndata dependencies.

## Acceptance Criteria
- [ ] `run_cellranger_count` with mocked subprocess returns `CellRangerCountOutput` with `summary_stats` populated from fixture.
- [ ] `CellRangerCountOutput.summary_stats` includes `estimated_cells`, `median_genes_per_cell`.
- [ ] `run_scanpy_pipeline` with mocked subprocess returns `ScanpyOutput` with `cluster_summary.n_clusters`.
- [ ] `scanpy_pipeline.py` can be called standalone: `python src/scripts/scanpy_pipeline.py --help` succeeds.
- [ ] `examples/scrnaseq/download_pbmc3k.sh` is runnable and well-documented.
- [ ] Notebook `analysis.ipynb` renders without errors using the downloaded PBMC 3k dataset (manual verification).

## Definition of Done
`pytest tests/tools/test_cellranger.py tests/tools/test_scanpy.py` green.
Example notebook documented and manually verified to run.
