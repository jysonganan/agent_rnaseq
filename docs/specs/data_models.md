# Data Models Specification

## ORM: SQLAlchemy | Validation: Pydantic | DB: SQLite (dev) / PostgreSQL (prod)

---

## Core Entities

### 1. `ReferenceGenome`
Registered reference genome configurations.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | VARCHAR(64) | UNIQUE, NOT NULL | Human label, e.g. `GRCh38_v43` |
| `species` | VARCHAR(64) | NOT NULL | e.g. `homo_sapiens` |
| `build` | VARCHAR(32) | NOT NULL | e.g. `GRCh38` |
| `annotation_version` | VARCHAR(32) | | e.g. `GENCODE_v43` |
| `fasta_path` | TEXT | NOT NULL | Local path or `s3://` URI |
| `gtf_path` | TEXT | NOT NULL | Gene annotation GTF |
| `star_index_path` | TEXT | | Pre-built STAR genome index |
| `star_txome_index_path` | TEXT | | STAR transcriptome index |
| `salmon_index_path` | TEXT | | Salmon index |
| `rsem_index_path` | TEXT | | RSEM index |
| `created_at` | TIMESTAMP | NOT NULL | |

---

### 2. `Project`
Logical grouping of related analysis runs.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `name` | VARCHAR(128) | NOT NULL | |
| `description` | TEXT | | |
| `owner` | VARCHAR(64) | NOT NULL | User/team identifier |
| `created_at` | TIMESTAMP | NOT NULL | |
| `updated_at` | TIMESTAMP | NOT NULL | |

---

### 3. `Sample`
A single biological sample with one or more FASTQ files.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `project_id` | UUID | FK → Project | |
| `name` | VARCHAR(128) | NOT NULL | |
| `sample_type` | ENUM | NOT NULL | `bulk_rnaseq`, `scrna_seq` |
| `condition` | VARCHAR(64) | | Experimental condition label |
| `replicate` | INTEGER | | Replicate number |
| `fastq_r1_path` | TEXT | NOT NULL | |
| `fastq_r2_path` | TEXT | | Null for single-end |
| `is_paired_end` | BOOLEAN | NOT NULL | |
| `metadata` | JSONB | | Arbitrary sample metadata |
| `created_at` | TIMESTAMP | NOT NULL | |

---

### 4. `AnalysisRun`
One end-to-end pipeline execution.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `project_id` | UUID | FK → Project | |
| `genome_id` | UUID | FK → ReferenceGenome | |
| `name` | VARCHAR(128) | NOT NULL | |
| `status` | ENUM | NOT NULL | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `pipeline_type` | ENUM | NOT NULL | `bulk_rnaseq`, `scrna_seq` |
| `alignment_mode` | ENUM | NOT NULL | `genome`, `transcriptome`, `both` |
| `aligner` | ENUM | NOT NULL | `star`, `salmon`, `rsem` |
| `run_config` | JSONB | NOT NULL | Full RunConfig snapshot |
| `agent_state` | JSONB | | LangGraph state checkpoint |
| `error_message` | TEXT | | Set on failure |
| `started_at` | TIMESTAMP | | |
| `completed_at` | TIMESTAMP | | |
| `created_at` | TIMESTAMP | NOT NULL | |
| `created_by` | UUID | FK → APIKey, NOT NULL | API key that created this run |

---

### 5. `RunSample`
Many-to-many: samples included in a run.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `run_id` | UUID | FK → AnalysisRun | Composite PK |
| `sample_id` | UUID | FK → Sample | Composite PK |

---

### 6. `PipelineStage`
Individual stage execution record within a run.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `run_id` | UUID | FK → AnalysisRun | |
| `sample_id` | UUID | FK → Sample | Null for multi-sample stages |
| `stage_name` | ENUM | NOT NULL | `qc`, `alignment`, `quantification`, `variant_calling`, `splicing`, `differential_expression`, `gsea`, `visualization`, `report` |
| `status` | ENUM | NOT NULL | `pending`, `running`, `completed`, `failed`, `skipped` |
| `tool_name` | VARCHAR(64) | NOT NULL | e.g. `star`, `deseq2` |
| `tool_version` | VARCHAR(32) | | |
| `input_params` | JSONB | | Validated tool input |
| `output_summary` | JSONB | | Validated tool output summary |
| `executor` | ENUM | | `local`, `nextflow`, `aws_batch` |
| `batch_job_id` | VARCHAR(128) | | AWS Batch job ID if applicable |
| `exit_code` | INTEGER | | Process exit code; 0 = success |
| `log_path` | TEXT | | |
| `started_at` | TIMESTAMP | | |
| `completed_at` | TIMESTAMP | | |

---

### 7. `Artifact`
Output files produced by pipeline stages.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `run_id` | UUID | FK → AnalysisRun | Denormalized for fast queries |
| `artifact_type` | ENUM | NOT NULL | `fastqc_report`, `bam`, `bai`, `counts_matrix`, `vcf`, `de_table`, `gsea_result`, `splicing_table`, `ucsc_track`, `html_report`, `streamlit_data` |
| `path` | TEXT | NOT NULL | Local path or `s3://` URI |
| `file_size_bytes` | BIGINT | | |
| `checksum_md5` | VARCHAR(32) | | |
| `created_at` | TIMESTAMP | NOT NULL | |

---

### 8. `QCMetric`
Parsed QC metric values (from FastQC, RSeQC, MultiQC).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `sample_id` | UUID | FK → Sample | |
| `metric_name` | VARCHAR(64) | NOT NULL | e.g. `pct_duplication`, `median_insert_size` |
| `metric_value` | FLOAT | | |
| `metric_value_str` | VARCHAR(256) | | For non-numeric metrics |
| `pass_fail` | ENUM | | `pass`, `warn`, `fail` |

---

### 9. `DEGResult`
Differentially expressed gene results (DESeq2 output).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `run_id` | UUID | FK → AnalysisRun | |
| `contrast` | VARCHAR(128) | NOT NULL | e.g. `treatment_vs_control` |
| `gene_id` | VARCHAR(64) | NOT NULL | Ensembl gene ID |
| `gene_name` | VARCHAR(64) | | |
| `basemean` | FLOAT | | |
| `log2_fold_change` | FLOAT | | |
| `lfcse` | FLOAT | | LFC standard error |
| `stat` | FLOAT | | Wald statistic |
| `pvalue` | FLOAT | | |
| `padj` | FLOAT | | Adjusted p-value (BH) |

---

### 10. `GSEAResult`
Pathway enrichment results (Reactome).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `run_id` | UUID | FK → AnalysisRun | |
| `contrast` | VARCHAR(128) | NOT NULL | |
| `pathway_id` | VARCHAR(64) | NOT NULL | Reactome pathway ID |
| `pathway_name` | TEXT | NOT NULL | |
| `nes` | FLOAT | | Normalized Enrichment Score |
| `pvalue` | FLOAT | | |
| `padj` | FLOAT | | |
| `leading_edge_genes` | TEXT | | Comma-separated gene list |

---

### 11. `SplicingResult`
Differential splicing events from rMATS.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `run_id` | UUID | FK → AnalysisRun | Denormalized for fast queries |
| `contrast` | VARCHAR(128) | NOT NULL | e.g. `treatment_vs_control` |
| `event_type` | ENUM | NOT NULL | `SE`, `A5SS`, `A3SS`, `MXE`, `RI` |
| `gene_id` | VARCHAR(64) | NOT NULL | Ensembl gene ID |
| `gene_name` | VARCHAR(64) | | |
| `inclusion_level_diff` | FLOAT | | IncLevelDifference from rMATS |
| `pvalue` | FLOAT | | |
| `fdr` | FLOAT | | FDR-adjusted p-value |

---

### 13. `VariantCall`
Variant records from GATK.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `sample_id` | UUID | FK → Sample | |
| `chrom` | VARCHAR(32) | NOT NULL | |
| `pos` | INTEGER | NOT NULL | 1-based position |
| `ref` | TEXT | NOT NULL | |
| `alt` | TEXT | NOT NULL | |
| `qual` | FLOAT | | |
| `filter` | VARCHAR(64) | | PASS or filter label |
| `info` | JSONB | | Parsed INFO fields |

---

### 12. `Conversation`
Chat conversation thread grouping a series of user and agent messages.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `title` | VARCHAR(256) | NOT NULL | Auto-generated from first user message (truncated to 60 chars) |
| `created_by` | UUID | FK → APIKey, NOT NULL | Key that created the conversation |
| `created_at` | TIMESTAMP | NOT NULL | |
| `updated_at` | TIMESTAMP | NOT NULL | Updated on each new message |

---

### 13. `ChatMessage`
Individual message within a conversation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `conversation_id` | UUID | FK → Conversation, NOT NULL | Parent conversation |
| `role` | ENUM | NOT NULL | `user`, `assistant`, `tool` |
| `content` | TEXT | NOT NULL | Markdown text (user/assistant) or JSON summary (tool) |
| `run_id` | UUID | FK → AnalysisRun | Set when message triggers or references a run |
| `tool_name` | VARCHAR(64) | | For role=tool messages: which tool was called |
| `tool_status` | ENUM | | `pending`, `running`, `completed`, `failed` |
| `created_at` | TIMESTAMP | NOT NULL | |

**Constraints:**
- `content` for `role=assistant` must never contain raw numerical pipeline output — only LLM-generated prose summaries of validated `ToolOutput` objects.
- `content` for `role=tool` is the JSON serialization of the corresponding `ToolOutput` Pydantic model summary.

---

### 14. `APIKey`
API key credentials for authentication.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `key_hash` | VARCHAR(64) | UNIQUE, NOT NULL | SHA-256 of the raw key; raw key never stored |
| `name` | VARCHAR(128) | NOT NULL | Human label for the key |
| `created_by` | VARCHAR(64) | NOT NULL | Admin user who issued the key |
| `created_at` | TIMESTAMP | NOT NULL | |
| `expires_at` | TIMESTAMP | | Null = no expiry |
| `revoked_at` | TIMESTAMP | | Non-null = revoked |

---

### 15. `scRNAClusterResult`
Cluster-level summary from Scanpy/Seurat analysis.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK | |
| `stage_id` | UUID | FK → PipelineStage | |
| `run_id` | UUID | FK → AnalysisRun | |
| `sample_id` | UUID | FK → Sample | |
| `n_clusters` | INTEGER | NOT NULL | |
| `cluster_id` | INTEGER | NOT NULL | Cluster label |
| `n_cells` | INTEGER | NOT NULL | Cells in cluster |
| `top_marker_genes` | TEXT | | Comma-separated gene list |

---

## Pydantic Schema Hierarchy (Python)

```
RunConfig
├── SampleConfig[]
├── GenomeConfig (references ReferenceGenome.id)
├── AlignmentConfig
├── QuantificationConfig
├── VariantCallingConfig
├── DEConfig
├── GSEAConfig
└── ExecutionConfig (local | nextflow | aws_batch)

ToolInput / ToolOutput (one pair per tool, see tool_contracts.md)
StageState (LangGraph node state)
RunState (top-level LangGraph state)
```

## Enum Definitions

```python
SampleType:    bulk_rnaseq | scrna_seq
RunStatus:     pending | running | completed | failed | cancelled
PipelineType:  bulk_rnaseq | scrna_seq
AlignmentMode: genome | transcriptome | both
QuantificationMethod: star_htseq | salmon | rsem
# Note: "star_htseq" = STAR alignment + HTSeq counting; salmon/rsem = direct quasi-mapping or RSEM.
# The Aligner is always STAR for bulk RNA-seq. QuantificationMethod determines the count tool.
StageName:     qc | alignment | quantification | variant_calling |
               splicing | differential_expression | gsea |
               scrna_seq | visualization | report
StageStatus:   pending | running | completed | failed | skipped
ArtifactType:  fastqc_report | bam | bai | counts_matrix | vcf |
               de_table | gsea_result | splicing_table | ucsc_track |
               html_report | streamlit_data | scrna_h5ad | scrna_umap | marker_genes
Executor:      local | nextflow | aws_batch
PassFail:      pass | warn | fail
MessageRole:   user | assistant | tool
ToolStatus:    pending | running | completed | failed
```
