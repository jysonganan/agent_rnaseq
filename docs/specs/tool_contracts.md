# Tool Contracts Specification

## Convention
- Every tool is a deterministic Python function: `tool_fn(input: XInput) -> XOutput`
- Inputs and outputs are Pydantic models — validated before and after every call.
- Tools may raise `ToolExecutionError` (with `exit_code`, `stderr`) — agents handle failures, never suppress them.
- Tools never call an LLM; LLMs never perform arithmetic directly.
- All path fields accept local absolute paths OR `s3://bucket/key` URIs.

---

## 1. QC Tools

### `run_fastqc`
Runs FastQC on one or more FASTQ files.

**Input: `FastQCInput`**
```python
fastq_paths: list[str]       # 1 or 2 files (R1, R2)
output_dir: str
threads: int = 4
```

**Output: `FastQCOutput`**
```python
report_html_paths: list[str]
report_zip_paths: list[str]
summary: dict[str, str]      # module_name -> PASS/WARN/FAIL
```

---

### `run_multiqc`
Aggregates QC reports from FastQC, STAR logs, etc.

**Input: `MultiQCInput`**
```python
input_dirs: list[str]
output_dir: str
report_name: str = "multiqc_report"
```

**Output: `MultiQCOutput`**
```python
report_html_path: str
data_dir: str
parsed_metrics: dict          # Sample → metric → value
```

---

### `run_rseqc`
Runs RSeQC post-alignment QC modules.

**Input: `RSeQCInput`**
```python
bam_path: str
bam_index_path: str
bed_annotation_path: str      # BED12 gene model
output_prefix: str
modules: list[str] = ["read_distribution", "infer_experiment", "junction_saturation"]
```

**Output: `RSeQCOutput`**
```python
module_outputs: dict[str, str]   # module_name → output file path
read_distribution: dict          # region → read_count (if run)
infer_experiment_result: dict    # strand inference result (if run)
```

---

## 2. Alignment Tools

### `run_star_align`
Aligns reads to genome or transcriptome using STAR.

**Input: `STARAlignInput`**
```python
fastq_r1: str
fastq_r2: str | None
genome_dir: str                  # STAR genome index directory
output_prefix: str
run_mode: Literal["alignReads"]  # extensible
threads: int = 8
extra_args: list[str] = []
quantification_mode: Literal["None", "TranscriptomeSAM", "GeneCounts"] = "GeneCounts"
out_sam_type: str = "BAM SortedByCoordinate"
```

**Output: `STARAlignOutput`**
```python
bam_path: str
bam_index_path: str
log_final_path: str
splice_junctions_path: str
gene_counts_path: str | None     # present when quantification_mode=GeneCounts
transcriptome_bam_path: str | None
alignment_stats: dict            # parsed from Log.final.out
  # uniquely_mapped_pct: float
  # multi_mapped_pct: float
  # unmapped_pct: float
  # total_reads: int
```

---

### `run_samtools_sort_index`
Sorts and indexes a BAM file.

**Input: `SamtoolsInput`**
```python
bam_path: str
output_prefix: str
threads: int = 4
```

**Output: `SamtoolsOutput`**
```python
sorted_bam_path: str
bai_path: str
flagstat: dict                  # parsed flagstat output
```

---

## 3. Quantification Tools

### `run_htseq_count`
Counts reads per gene using HTSeq-count.

**Input: `HTSeqInput`**
```python
bam_path: str
gtf_path: str
output_path: str
stranded: Literal["yes", "no", "reverse"] = "reverse"
mode: Literal["union", "intersection-strict", "intersection-nonempty"] = "union"
additional_args: list[str] = []
```

**Output: `HTSeqOutput`**
```python
counts_path: str                 # TSV: gene_id, count
total_reads: int
counted_reads: int
no_feature_reads: int
ambiguous_reads: int
```

---

### `run_salmon_quant`
Quasi-mapping quantification with Salmon.

**Input: `SalmonQuantInput`**
```python
fastq_r1: str
fastq_r2: str | None
index_path: str
output_dir: str
lib_type: str = "A"             # Auto-detect library type
threads: int = 8
extra_args: list[str] = []
```

**Output: `SalmonQuantOutput`**
```python
quant_sf_path: str              # transcript-level TPM/NumReads
lib_format_counts_path: str
meta_info_path: str
eq_classes_path: str | None
inferred_lib_type: str
mapping_rate: float
```

---

### `run_rsem`
Gene/isoform quantification with RSEM.

**Input: `RSEMInput`**
```python
bam_path: str                   # Transcriptome-aligned BAM
rsem_reference: str
output_prefix: str
paired_end: bool = True
threads: int = 8
extra_args: list[str] = []
```

**Output: `RSEMOutput`**
```python
genes_results_path: str         # gene FPKM/TPM/expected_count
isoforms_results_path: str
stat_dir: str
```

---

## 4. Variant Calling Tools

### `run_gatk_haplotypecaller`
Variant calling with GATK HaplotypeCaller.

**Input: `GATKHaplotypeCallerInput`**
```python
bam_path: str
bam_index_path: str
reference_fasta: str
output_vcf_path: str
dbsnp_path: str | None
interval_list: str | None
emit_ref_confidence: Literal["NONE", "BP_RESOLUTION", "GVCF"] = "NONE"
extra_args: list[str] = []
```

**Output: `GATKHaplotypeCallerOutput`**
```python
vcf_path: str
vcf_index_path: str
variant_count: int
```

---

### `run_gatk_variant_filter`
Applies hard filters to a VCF.

**Input: `GATKVariantFilterInput`**
```python
vcf_path: str
reference_fasta: str
output_vcf_path: str
snp_filter_expression: str       # e.g. "QD < 2.0 || FS > 60.0"
indel_filter_expression: str
```

**Output: `GATKVariantFilterOutput`**
```python
filtered_vcf_path: str
filtered_vcf_index_path: str
pass_variant_count: int
filtered_variant_count: int
```

---

## 5. Splicing Analysis Tools

### `run_rmats`
Differential splicing analysis with rMATS.

**Input: `RMATSInput`**
```python
bam_list_b1: list[str]          # BAMs for condition 1
bam_list_b2: list[str]          # BAMs for condition 2
gtf_path: str
output_dir: str
read_length: int
paired_stats: bool = True
novelSS: bool = False
extra_args: list[str] = []
```

**Output: `RMATSOutput`**
```python
output_dir: str
event_types: list[str]           # SE, A5SS, A3SS, MXE, RI
significant_events_count: dict[str, int]   # event_type -> count
summary_path: str
```

---

## 6. Differential Expression Tools

### `run_deseq2`
Differential expression analysis with DESeq2 (R subprocess).

**Input: `DESeq2Input`**
```python
counts_matrix_path: str          # Gene x Sample count matrix (CSV/TSV)
sample_metadata_path: str        # CSV: sample_id, condition, [covariates]
contrasts: list[DEContrast]      # list of {name, numerator, denominator}
output_dir: str
min_count: int = 10
alpha: float = 0.05
lfc_threshold: float = 0.0
r_script_path: str               # Path to validated R script
```

**`DEContrast`**
```python
name: str
numerator: str
denominator: str
```

**Output: `DESeq2Output`**
```python
results_paths: dict[str, str]   # contrast_name -> CSV path
normalized_counts_path: str
size_factors_path: str
dispersion_plot_path: str
pca_plot_path: str
contrast_summaries: dict[str, DEContrastSummary]
```

**`DEContrastSummary`**
```python
total_genes: int
upregulated: int
downregulated: int
not_significant: int
```

---

## 7. GSEA / Pathway Enrichment Tools

### `run_reactome_gsea`
Gene set enrichment analysis using Reactome (R/fgsea subprocess).

**Input: `ReactomeGSEAInput`**
```python
de_results_path: str             # DESeq2 output CSV
contrast_name: str
output_dir: str
organism: str = "human"          # human | mouse
rank_metric: Literal["stat", "log2fc_signed"] = "stat"
nperm: int = 1000
r_script_path: str
```

**Output: `ReactomeGSEAOutput`**
```python
results_path: str                # CSV: pathway_id, pathway_name, NES, pvalue, padj
enrichment_plots_dir: str
significant_pathway_count: int
```

---

## 8. Single-Cell Tools

### `run_cellranger_count`
CellRanger count for 10x Genomics data.

**Input: `CellRangerCountInput`**
```python
fastq_dirs: list[str]
sample_name: str
transcriptome_path: str
output_dir: str
expected_cells: int | None
localcores: int = 8
localmem: int = 64
```

**Output: `CellRangerCountOutput`**
```python
output_dir: str
filtered_matrix_dir: str         # barcodes.tsv.gz, features.tsv.gz, matrix.mtx.gz
molecule_info_path: str
summary_html_path: str
summary_stats: dict              # estimated_cells, median_genes_per_cell, etc.
```

---

### `run_scanpy_pipeline`
Scanpy single-cell preprocessing, clustering, and UMAP (Python subprocess).

**Input: `ScanpyInput`**
```python
matrix_dir: str                  # CellRanger output
output_dir: str
min_genes: int = 200
min_cells: int = 3
max_pct_mt: float = 20.0
n_top_genes: int = 2000
n_neighbors: int = 15
script_path: str
```

**Output: `ScanpyOutput`**
```python
h5ad_path: str                   # AnnData object
umap_plot_path: str
marker_genes_path: str
cluster_summary: dict            # n_clusters, cells_per_cluster
```

---

## 9. Visualization Tools

### `prepare_streamlit_data`
Aggregates pipeline results into Streamlit-ready data files.

**Input: `StreamlitDataPrepInput`**
```python
run_id: str
de_results_dir: str | None
gsea_results_dir: str | None
qc_metrics_path: str | None
output_dir: str
```

**Output: `StreamlitDataPrepOutput`**
```python
output_dir: str
manifest_path: str               # JSON listing available data files
```

---

### `generate_ucsc_tracks`
Generates UCSC genome browser track files (bigWig, bigBed).

**Input: `UCSCTrackInput`**
```python
bam_paths: list[str]
genome_build: str                # e.g. hg38, mm10
output_dir: str
track_name_prefix: str
chrom_sizes_path: str
```

**Output: `UCSCTrackOutput`**
```python
bigwig_paths: list[str]
track_hub_path: str              # trackDb.txt
```

---

## 10. Report Tools

### `compile_report`
Assembles final HTML/Markdown analysis report.

**Input: `ReportInput`**
```python
run_id: str
run_name: str
qc_summary: dict | None
de_summary: dict | None
gsea_summary: dict | None
artifact_paths: dict[str, str]
output_dir: str
template_path: str
```

**Output: `ReportOutput`**
```python
html_report_path: str
markdown_report_path: str
```

---

## 11. AWS Tools

### `submit_aws_batch_job`
Submits a containerized job to AWS Batch.

**Input: `BatchJobInput`**
```python
job_name: str
job_queue: str
job_definition: str
container_overrides: dict        # command, environment, resourceRequirements
depends_on: list[str] = []      # job IDs
```

**Output: `BatchJobOutput`**
```python
job_id: str
job_arn: str
status: str
```

---

### `poll_aws_batch_job`
Polls status of an AWS Batch job.

**Input: `BatchPollInput`**
```python
job_id: str
```

**Output: `BatchPollOutput`**
```python
job_id: str
status: Literal["SUBMITTED", "PENDING", "RUNNABLE", "STARTING", "RUNNING", "SUCCEEDED", "FAILED"]
status_reason: str | None
exit_code: int | None
log_stream_name: str | None
```

---

## Error Types

```python
class ToolExecutionError(Exception):
    tool_name: str
    exit_code: int
    stderr: str
    command: list[str]

class ToolValidationError(Exception):
    tool_name: str
    field: str
    message: str

class ToolTimeoutError(Exception):
    tool_name: str
    timeout_seconds: int
```

## Stage Dependencies

The Orchestrator must reject any `RunConfig` whose `stages` list violates these dependencies:

| Stage | Requires |
|---|---|
| `alignment` | (warns if `qc` absent, but not blocked) |
| `quantification` | `alignment` |
| `differential_expression` | `quantification` |
| `gsea` | `differential_expression` |
| `splicing` | `alignment` |
| `variant_calling` | `alignment` |
| `visualization` | at least one of: `differential_expression`, `gsea`, `qc` |
| `report` | at least one upstream stage complete |
| `scrna_seq` | none (parallel to bulk pipeline) |

Validation must occur in `OrchestratorAgent` before dispatching to LangGraph.

---

## Mock Tool Registry

When `RunConfig.dry_run = True` (dev/test mode only; not settable by LLM; must be set in API request body), all tool calls return pre-defined fixture outputs instead of executing real processes.

Fixture files live in `tests/fixtures/mock_tool_outputs/`:
```
fastqc_output.json
multiqc_output.json
rseqc_output.json
star_align_output.json
samtools_output.json
htseq_output.json
salmon_quant_output.json
rsem_output.json
gatk_haplotypecaller_output.json
gatk_variant_filter_output.json
rmats_output.json
deseq2_output.json
reactome_gsea_output.json
cellranger_count_output.json
scanpy_output.json
```

Each fixture is a JSON serialization of the corresponding `ToolOutput` Pydantic model. The `MockToolRegistry` in `src/tools/mock_registry.py` maps tool function names to fixture paths and is injected at the `BaseStageAgent` level when `dry_run=True`.

---

## Versioning
Tool contracts are versioned alongside the codebase.
Any breaking change to an Input or Output schema requires a new task and review.
