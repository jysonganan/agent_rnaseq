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
infer_experiment_result: dict    # strand inference result (if run), see below
```

`infer_experiment_result` keys: `library_type` (`PairEnd` | `SingleEnd` | `Unknown`),
`undetermined`, `sense`, `antisense` (fractions as printed by RSeQC; `sense` is
`"1++,1--,2+-,2-+"` for paired-end or `"++,--"` for single-end, `antisense` is
`"1+-,1-+,2++,2--"` or `"+-,-+"`), and `strandedness`, a deterministic label from
`f = sense / (sense + antisense)`:

| Condition | `strandedness` | Equivalent |
|---|---|---|
| `sense + antisense == 0` | `undetermined` | |
| `f ≥ 0.8` | `forward` | HTSeq `--stranded yes`, Salmon `SF`/`ISF` |
| `f ≤ 0.2` | `reverse` | HTSeq `--stranded reverse`, Salmon `SR`/`ISR` (dUTP) |
| `0.4 ≤ f ≤ 0.6` | `unstranded` | HTSeq `--stranded no`, Salmon `U`/`IU` |
| otherwise | `ambiguous` | |

RSeQC runs in the `alignment_qc` stage (after `alignment`), never in `qc`, which runs before
any BAM exists. The stage runs `read_distribution` and `infer_experiment`.

---

### `convert_gtf_to_bed12`
Deterministic GTF → BED12 conversion (no external tools), used by `alignment_qc` when the
genome has no `bed_annotation_path`.

```python
convert_gtf_to_bed12(gtf_path: str, bed_path: str) -> int   # returns transcripts written
```

- Reads plain or gzipped GTF. One BED12 line per `transcript_id` that has `exon` features.
- Coordinates: GTF 1-based closed → BED 0-based half-open. Exons sorted by start; blocks are
  the exons. `thickStart`/`thickEnd` span the transcript's `CDS` + `start_codon` +
  `stop_codon` features; transcripts without them get `thickStart = thickEnd = chromStart`
  (non-coding).
- A transcript whose exons span several chromosomes or strands is skipped.
- Output sorted by chromosome, start, name. Written to a temporary file and renamed, so a
  partial BED is never read.

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
alignment_mode: Literal["genome", "transcriptome", "both"] = "genome"
read_group_id: str | None        # → --outSAMattrRGline ID:<id> SM:<sample> PL:ILLUMINA
read_group_sample: str | None    #   (defaults to read_group_id); [A-Za-z0-9_.:-]{1,128}
```
The executor sets the read group to the sanitised sample name — GATK HaplotypeCaller rejects BAMs
without `@RG`.

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

### `build_count_matrix`
Merges per-sample quantification outputs into the gene x sample CSV consumed by
`run_deseq2`. Pure Python, no subprocess. Values are copied verbatim from the
tool outputs (no normalisation); genes absent from a sample are written as `0`.

**Input: `CountMatrixInput`**
```python
sample_count_paths: dict[str, str]   # sample_id -> per-sample quant file (insertion order = column order)
method: Literal["star_htseq", "salmon", "rsem"]
output_path: str                     # CSV written here
```
Per-method column read: htseq → 2nd column (rows starting `__` dropped);
salmon `quant.sf` → `NumReads`; rsem `genes.results` → `expected_count`.

**Output: `CountMatrixOutput`**
```python
counts_matrix_path: str
n_genes: int
n_samples: int
```

### `write_sample_metadata`
Writes the `sample_id,condition` CSV consumed by `run_deseq2`.

**Input: `SampleMetadataInput`**
```python
sample_conditions: dict[str, str]    # sample_id -> condition (min 2 samples)
output_path: str
```

**Output:** `str` — the written path.

Raises `ToolValidationError` on an empty/missing condition or fewer than two distinct conditions.

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
Aggregates pipeline results into Streamlit-ready data files. Pure Python; copies values verbatim
from tool outputs (no recomputation).

**Input: `StreamlitDataPrepInput`**
```python
run_id: str
de_results_dir: str | None
gsea_results_dir: str | None
qc_metrics_path: str | None
output_dir: str
```

Input semantics: `de_results_dir` holds DESeq2 `<contrast>_results.csv` files;
`gsea_results_dir` holds `<contrast>/gsea_results.csv`; `qc_metrics_path` is a JSON file
`{"samples": [{"sample": str, "total_reads": int, "mapping_rate": float, "fastqc_pass": int,
"fastqc_warn": int, "fastqc_fail": int}, ...]}` written by the stage executor from validated QC /
alignment outputs. All inputs are optional; missing ones are simply not listed.

**Output: `StreamlitDataPrepOutput`**
```python
output_dir: str
manifest_path: str               # JSON listing available data files
```

Files written to `output_dir`: `de_results.csv` (all contrasts, extra column `contrast`),
`gsea_results.csv` (all contrasts, extra column `contrast`), `qc_metrics.json`, and
`manifest.json` = `{"run_id": str, "available": {"de_results"?: "de_results.csv",
"gsea_results"?: "gsea_results.csv", "qc_metrics"?: "qc_metrics.json"}}` — the format read by
`src/streamlit/data_loader.py`. Raises `ToolValidationError` if a DE/GSEA CSV lacks the expected
header columns.

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

`chrom_sizes_path` is optional (not needed by `bamCoverage`, which reads the BAM header); kept
for future bedGraph-based tracks.

Implementation: one deepTools `bamCoverage --normalizeUsing CPM --binSize 10` subprocess per BAM
(BAM index must exist next to it), then a UCSC track hub (`hub.txt`, `genomes.txt`,
`<genome_build>/trackDb.txt`) referencing the bigWigs by relative URL.

**Output: `UCSCTrackOutput`**
```python
bigwig_paths: list[str]
track_hub_path: str              # <output_dir>/<genome_build>/trackDb.txt (hub.txt is in output_dir)
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

Input semantics (all values come from validated tool outputs — never LLM text):
- `qc_summary`: `{sample_id: FastQCOutput dict}` → per-sample PASS/WARN/FAIL module counts.
- `de_summary`: `{contrast: DEContrastSummary dict}` → genes tested / up / down per contrast.
- `gsea_summary`: `{contrast: {"significant_pathway_count": int}}`.
- `artifact_paths`: `{label: path}` → listed by file name.
- `template_path`: HTML file with `string.Template` placeholders `$title` and `$body`.

Every interpolated value is HTML-escaped. Writes `report.md` and `report.html` into `output_dir`.

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
| `alignment_qc` | `alignment` |
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

Fixture files ship with the application in `src/tools/mock_outputs/` (package data — they must
be available in the API/worker image, not only in `tests/`), one per stage:
```
fastqc_output.json            → qc                       (FastQCOutput)
star_align_output.json        → alignment                (STARAlignOutput)
htseq_output.json             → quantification           (HTSeqOutput)
gatk_variant_filter_output.json → variant_calling        (GATKVariantFilterOutput)
rmats_output.json             → splicing                 (RMATSOutput)
deseq2_output.json            → differential_expression  (DESeq2Output)
reactome_gsea_output.json     → gsea                     (ReactomeGSEAOutput)
scanpy_output.json            → scrna_seq                (ScanpyOutput)
streamlit_prep_output.json    → visualization            (StreamlitDataPrepOutput)
report_output.json            → report                   (ReportOutput)
```

Each fixture is a JSON serialization of the corresponding `ToolOutput` Pydantic model and is
**validated against that model when loaded** (`src/tools/mock_registry.py::load_default_registry`),
so fixture drift fails loudly. The registry maps stage name → `StageOutput` dict (with
`"mock": true`) and is injected at the `BaseStageAgent` level when `dry_run=True`;
`execute_run` uses it by default for dry runs. Dry-run stages spawn no subprocesses and write no
per-stage DB rows; `RunState.stage_outputs` has the same shape as a real run.

---

## 11b. Stage Execution Contract (`OrchestratorAgent.execute_run`)

Not a tool — the deterministic bridge between the LangGraph graph and the specialist sub-agents.

```python
OrchestratorAgent(llm_client=None, dry_run=False).execute_run(
    db: Session, run_id: str, *, output_root: str | None = None,
    mock_registry: MockToolRegistry | None = None, events: RunEvents | None = None,
) -> RunState   # final graph state
```

- Raises `OrchestratorError` before any tool runs if: the run is missing, stages violate the
  dependency map, user analysis inputs are missing/inconsistent (`run_requirements.py`), or the
  executor's prerequisites are missing (see "Executors" below).
- Stage inputs are built by `src/agents/stage_inputs.py::build_stage_inputs(stage, ctx,
  stage_outputs)` from DB records and upstream outputs only (never LLM text):

| Stage | Invocations | Key inputs resolved from |
|---|---|---|
| `qc` | per sample | `Sample.fastq_*` (FastQC + MultiQC; pre-alignment) |
| `alignment` | per sample | `ReferenceGenome.star_index_path`; `alignment_mode` (forced to `both` for RSEM) |
| `alignment_qc` | per sample | sorted BAM + BAI from alignment; `ReferenceGenome.bed_annotation_path`, else a BED12 derived from `ReferenceGenome.gtf_path` into the run's `alignment_qc/gene_model/genes.bed12` (once per run) |
| `quantification` | per sample | method from `AnalysisRun.aligner`; sorted BAM / FASTQ / transcriptome BAM; genome GTF / Salmon / RSEM index |
| `variant_calling` | per sample | sorted BAM + BAI, genome FASTA, `run_config.dbsnp_path` |
| `scrna_seq` | per sample | `Sample.metadata.fastq_dirs`, `run_config.cellranger_transcriptome_path` |
| `splicing` | per user contrast | numerator/denominator BAMs, genome GTF, `read_length` |
| `differential_expression` | once | `build_count_matrix` + `write_sample_metadata` over all samples; user `de_contrasts`; `alpha`, `lfc_threshold` |
| `gsea` | once | DE `results_paths`; organism from `ReferenceGenome.species` (human/mouse) |
| `visualization` | once | DE/GSEA output dirs; a QC metrics JSON written from validated QC/alignment outputs; BAMs (+BAI) if aligned |
| `report` | once | DE `contrast_summaries`, GSEA `per_contrast` counts, QC outputs, artifact paths; `src/tools/report/template.html` |

- Specialists are called via `BaseSpecialistAgent.run_stage(input, compute=None, executor="local")`,
  which stores the input as `PipelineStage.input_params` and sets `started_at`, `completed_at`
  and `executor` (where the tools actually ran).
- **Artifact re-verification (Rule 10)**: before a stage's tools run, every input path that is a
  local `Artifact` of the same run with a recorded checksum is re-hashed
  (`src/agents/artifact_integrity.py`); a missing file or changed MD5 fails the stage.
- `RunState.stage_outputs[stage]` is `{"samples": {sample_id: StageOutput}}`,
  `{"contrasts": {name: StageOutput}}`, or a single `StageOutput`
  (`{stage_name, status, output, tool_version, summary}`); a failed per-item stage keeps its
  finished items plus `"partial": true` so a resume skips them.
- Failure semantics: the failing invocation's uncommitted rows are rolled back, a `failed`
  `PipelineStage` audit row is written with its `input_params`, `failed_stage` /
  `error_message` (sanitized, ≤1000 chars) are set, the graph ends.

### Executors

`run_config.execution.executor` selects where the **heavy per-sample stages** (`qc`,
`alignment`, `alignment_qc`, `quantification`, `variant_calling`) run. All other stages always run in the worker.

| Executor | Heavy stages | Outputs published to | Prerequisites (checked at start) |
|---|---|---|---|
| `local` | tool subprocesses in the worker | `{OUTPUT_ROOT}/{run_id}/{stage}/{sample_id}/` | — |
| `nextflow` | `nextflow run nextflow/main.nf -profile local` | same local paths | `nextflow` on the worker's PATH (`NEXTFLOW_BIN`) |
| `aws_batch` | `nextflow run nextflow/main.nf -profile awsbatch` (one Batch job per process) | `s3://{S3_ARTIFACT_BUCKET}/runs/{run_id}/{stage}/{sample_id}/` | `nextflow` on PATH, `S3_ARTIFACT_BUCKET`, `AWS_BATCH_JOB_QUEUE`, and `s3://` paths for every sample FASTQ, genome FASTA/GTF and STAR index |

Heavy specialists are split into `compute(stage_input) -> {role: ToolOutput}` and
`persist(stage, stage_input, outs) -> StageOutput`; the Nextflow backend replaces only
`compute`, so DB rows/artifacts are written by the same code for every executor.

### Nextflow backend (`src/tools/nextflow/stage_runner.py`)

`NextflowStageRunner.compute_for(stage)(stage_input)` runs one workflow for one sample:

```
nextflow -log <launch>/.nextflow.log run nextflow/main.nf -profile <local|awsbatch>
  -c <launch>/overrides.config -work-dir <local dir | s3://bucket/nextflow-work/<run_id>>
  --workflow <qc|alignment|alignment_qc|quantification|variant_calling> --sample_id <sample uuid>
  --output_dir <stage dir> --tools_image <NEXTFLOW_TOOLS_IMAGE> [--<param> <value> ...]
```

Also passed on every invocation: `--threads <execution.cpus>` and `--memory "<execution.memory_gb> GB"`
(module `cpus`/`memory` directives read these params, so the run's settings apply), and
`NEXTFLOW_EXTRA_ARGS` (e.g. `-stub-run`). The profile is `awsbatch` for `aws_batch` and
`NEXTFLOW_LOCAL_PROFILE` for `nextflow` (`local` = tools image via Docker; `localtools` = tools on
PATH, e.g. `environment/rnaseq-tools.yml`; append `,test` for tiny datasets).

`overrides.config` comes from `build_config_overrides(execution)` (executor, Batch queue, region,
work dir). All processes run in the project's tools image, so tool versions equal the local ones.
Each process writes `<sid>.<tool>.version.txt` (published); the adapters use its first line as
`tool_version`, falling back to `docker/tool_versions.txt`. Every module has a `stub:` block
producing parseable outputs, used by the CI stub run (`docs/testing/executor_e2e.md`). The worker polls the process,
terminates it on run cancellation, and on a non-zero exit raises `ToolExecutionError` with the
last 2000 bytes of Nextflow's output.

Published files (per sample `--output_dir`) and the ToolOutput built from them:

| Workflow | Params | Published files | ToolOutput(s) |
|---|---|---|---|
| `qc` | `fastq_r1`, `fastq_r2` | `<stem>_fastqc.{html,zip}` | `FastQCOutput` (summary read from the zip) |
| `alignment` | `fastq_r1`, `fastq_r2`, `genome_dir`, `alignment_mode`, `read_group` (@RG ID/SM; GATK needs it) | `<sid>_Log.final.out`, `<sid>_SJ.out.tab`, `<sid>.sorted.bam(.bai)`, `<sid>_Aligned.toTranscriptome.out.bam` (mode ≠ genome) | `STARAlignOutput` (stats parsed from the log), `SamtoolsOutput` |
| `alignment_qc` | `bam`, `bai`, `bed` (BED12) | `<sid>.rseqc_{read_distribution,infer_experiment}.txt` | `RSeQCOutput` (parsed from the two files) |
| `quantification` | `quant_mode` + `bam`,`gtf_path` (htseq) / `fastq_*`,`salmon_index` / `bam`,`rsem_reference` | `<sid>_counts.tsv` / `<sid>/quant.sf`, `<sid>/aux_info/meta_info.json` / `<sid>.{genes,isoforms}.results` | `HTSeqOutput` / `SalmonQuantOutput` / `RSEMOutput` |
| `variant_calling` | `bam`, `bai`, `reference_fasta` (`.fai`, `.dict` alongside) | `<sid>.{raw,filtered}.vcf.gz(.tbi)` | `GATKHaplotypeCallerOutput`, `GATKVariantFilterOutput` (counts parsed from the VCFs) |

For `alignment_qc` without a genome BED, the worker derives the BED12 from the GTF (downloading
an `s3://` GTF to the cache) and, with `aws_batch`, uploads it to
`s3://{S3_ARTIFACT_BUCKET}/runs/{run_id}/alignment_qc/gene_model/genes.bed12` so Batch jobs can
read it. A missing published file raises `ToolValidationError`. Only small files (logs, counts, FastQC
zips, VCFs, Salmon metadata) are read by the worker; with `aws_batch` they are downloaded to
`{OUTPUT_ROOT}/{run_id}/s3_cache/`. Worker-side consumers of remote files: DESeq2 (counts files)
and — when requested — `splicing` (rMATS) and `visualization` (bamCoverage), which **download
the BAMs** to the cache. Artifacts on S3 have no `checksum_md5` (not re-verified by the worker).


---

## 12. Chat Gateway Interface

The chat endpoint does not introduce new deterministic tools. However, the `OrchestratorAgent` exposes a typed method for processing chat messages:

### `OrchestratorAgent.dispatch_from_chat`

Not a standalone tool function — this is a method on `OrchestratorAgent` that bridges the chat UI to the existing deterministic tool layer.

**Input: `ChatDispatchInput`** (Pydantic model)
```python
conversation_id: str         # UUID of the Conversation record
message_id: str              # UUID of the ChatMessage (role=user) already saved
user_content: str            # Raw user natural-language message (max 4000 chars)
api_key_id: str              # UUID of the authenticated APIKey
```

**Output: `ChatDispatchOutput`** (Pydantic model)
```python
run_id: str | None           # UUID of created AnalysisRun; None if agent asked follow-up Q
assistant_message_id: str    # UUID of ChatMessage(role=assistant) created
needs_clarification: bool    # True if agent could not fully resolve RunConfig
clarification_prompt: str | None  # Follow-up question to display if needs_clarification=True
```

**Behaviour contract:**

**Sample and genome resolution (anti-hallucination constraint):**
Before calling the LLM, the method MUST:
1. Query the DB for all `Sample` records accessible to `api_key_id` (via project ownership).
2. Query the DB for all registered `ReferenceGenome` records.
3. Include both lists (id, name, condition, sample_type for samples; id, name, build for genomes) in the LLM system prompt as structured JSON.
4. The LLM MUST select `sample_ids` and `genome_id` by exact UUID match from these provided lists only. It must NEVER generate or infer UUIDs from free text.
5. After LLM selection, re-validate that every selected UUID exists in the DB before constructing RunConfig. Raise `ToolValidationError` if any ID is not found.

**LLM completion mode:** The intent-parsing and response-generation calls inside this method MUST use `stream=True` (streaming completions). Each streamed token chunk is published immediately as a `{ "type": "token", "payload": { "message_id": ..., "token": ... } }` frame to the Redis channel `conv:{conversation_id}`. This enables real-time token streaming in the chat UI.

**ChatMessage commit timing:** The arq worker accumulates all streamed tokens in memory. After the full response is assembled and the `done` frame has been published to Redis, the worker writes a single `ChatMessage(role=assistant, content=<full_accumulated_text>)` to the DB. If the worker crashes before this commit, the assistant message is absent from history (safe failure — the user can re-send). Partial commits are forbidden.

**tool_call frame summary field:** The `summary` field in `tool_call` WS frames MUST be a JSON-serialized excerpt of the validated `ToolOutput` Pydantic model (e.g., `{"significant_genes": 423, "total_genes": 18000}`). It must NOT be LLM-generated prose. LLM prose summaries appear only in `token` frames.

- **Conversation context:** the intent-parsing call receives the last 20 user/assistant messages of the conversation (oldest first) followed by `user_content`, so an answer to a clarification question completes the earlier request.
- **Analysis inputs are user decisions** (see `POST /runs` → "Analysis inputs"). The LLM may only copy contrasts and read length the user explicitly stated; it must never pick a comparison direction or a read length itself. Deterministic guards after parsing:
  - every contrast's `numerator`/`denominator` must be a condition of a selected sample **and** appear in the user's own messages (case-insensitive);
  - `read_length` must appear as a literal number in the user's own messages;
  - contrast `name` is always generated as `<numerator>_vs_<denominator>` (never LLM-authored).
  Values failing a guard are dropped; if a required input is then missing, the method asks for it with a **deterministic** question (no LLM) that lists the available conditions and their sample counts and gives the `<test> vs <reference>` format.
- If `user_content` is ambiguous, the method:
  1. Streams clarification question as `token` frames.
  2. Publishes `done` frame with `run_id: null`.
  3. Writes `ChatMessage(role=assistant)` with the clarification text.
  4. Returns `ChatDispatchOutput(run_id=None, needs_clarification=True, clarification_prompt=<text>)`.
  5. Does NOT create an `AnalysisRun`.
- If `user_content` resolves to a complete `RunConfig`:
  1. Pydantic-validates the RunConfig (same rules as `POST /runs`; same parameter guardrails from Rule 5).
  2. Sets `AnalysisRun.conversation_id` and `AnalysisRun.triggering_message_id` for audit trail.
  3. Creates `AnalysisRun`, enqueues arq pipeline job.
  4. Streams acknowledgement as `token` frames; publishes `done` frame with `run_id`.
  5. Writes `ChatMessage(role=assistant)` with acknowledgement text.
  6. Returns `ChatDispatchOutput(run_id=<uuid>, needs_clarification=False, ...)`.
- The method must never write LLM-generated numerical values to `AnalysisRun.run_config`; all numerical parameters come from Pydantic defaults or validated user-specified values.
- Redis channel for streaming: `conv:{conversation_id}`.

---

## Versioning
Tool contracts are versioned alongside the codebase.
Any breaking change to an Input or Output schema requires a new task and review.
