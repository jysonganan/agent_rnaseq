# TASK-10: Agent Layer — Specialist Sub-Agents

## Goal
Implement all specialist sub-agents that own individual pipeline stages. Each sub-agent: receives typed `StageInput` from LangGraph state, calls deterministic tools, validates outputs, writes DB records, updates state.

## Requirements
Implement one class per stage, all inheriting from `BaseStageAgent` (TASK-09):

| Agent class | Stage | Primary tools |
|---|---|---|
| `QCAgent` | qc | `run_fastqc`, `run_rseqc`, `run_multiqc` |
| `AlignmentAgent` | alignment | `run_star_align`, `run_samtools_sort_index` |
| `QuantificationAgent` | quantification | `run_htseq_count` or `run_salmon_quant` or `run_rsem` (per config) |
| `VariantAgent` | variant_calling | `run_gatk_haplotypecaller`, `run_gatk_variant_filter` |
| `SplicingAgent` | splicing | `run_rmats` |
| `DEAgent` | differential_expression | `run_deseq2` |
| `GSEAAgent` | gsea | `run_reactome_gsea` |
| `scRNAAgent` | scrna_seq | `run_cellranger_count`, `run_scanpy_pipeline` |
| `VizAgent` | visualization | `prepare_streamlit_data`, `generate_ucsc_tracks` |
| `ReportAgent` | report | `compile_report` |

Each agent:
- Writes a `PipelineStage` record at start (status=running) and updates it on completion/failure.
- Writes `Artifact` records for each output file.
- Writes domain result records (e.g. `DEGResult`, `GSEAResult`, `QCMetric`) after tool call.
- Returns `StageOutput` to LangGraph state.
- LLM call (if any) is for natural language summary only, using typed `StageOutput` as input.

## Files to Create
```
src/agents/specialists/
  __init__.py
  qc_agent.py
  alignment_agent.py
  quantification_agent.py
  variant_agent.py
  splicing_agent.py
  de_agent.py
  gsea_agent.py
  scrna_agent.py
  viz_agent.py
  report_agent.py
tests/agents/specialists/
  __init__.py
  test_qc_agent.py
  test_alignment_agent.py
  test_de_agent.py
  test_gsea_agent.py
  (others follow same pattern)
```

## Acceptance Criteria
- [ ] Each agent can be instantiated and its `run(stage_input)` method called with mocked tools.
- [ ] Each agent writes a `PipelineStage` record on start; updates to `completed` on success.
- [ ] Each agent updates stage to `failed` on `ToolExecutionError`; exception does not propagate silently.
- [ ] `DEAgent` bulk-inserts `DEGResult` rows from `DESeq2Output`; no LLM-generated values in those rows.
- [ ] `GSEAAgent` bulk-inserts `GSEAResult` rows from `ReactomeGSEAOutput`.
- [ ] `QCAgent` writes `QCMetric` rows from parsed FastQC/RSeQC output.
- [ ] `QuantificationAgent` selects tool (`htseq`, `salmon`, or `rsem`) based on `RunConfig.aligner`.
- [ ] LLM summary calls are mocked in all unit tests.

## Definition of Done
`pytest tests/agents/specialists/` green. Tool calls mocked, DB via in-memory SQLite.
