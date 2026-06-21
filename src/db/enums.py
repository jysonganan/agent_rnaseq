import enum


class SampleType(enum.StrEnum):
    bulk_rnaseq = "bulk_rnaseq"
    scrna_seq = "scrna_seq"


class RunStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class PipelineType(enum.StrEnum):
    bulk_rnaseq = "bulk_rnaseq"
    scrna_seq = "scrna_seq"


class AlignmentMode(enum.StrEnum):
    genome = "genome"
    transcriptome = "transcriptome"
    both = "both"


class Aligner(enum.StrEnum):
    star = "star"
    salmon = "salmon"
    rsem = "rsem"


class QuantificationMethod(enum.StrEnum):
    star_htseq = "star_htseq"
    salmon = "salmon"
    rsem = "rsem"


class StageName(enum.StrEnum):
    qc = "qc"
    alignment = "alignment"
    quantification = "quantification"
    variant_calling = "variant_calling"
    splicing = "splicing"
    differential_expression = "differential_expression"
    gsea = "gsea"
    scrna_seq = "scrna_seq"
    visualization = "visualization"
    report = "report"


class StageStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class ArtifactType(enum.StrEnum):
    fastqc_report = "fastqc_report"
    bam = "bam"
    bai = "bai"
    counts_matrix = "counts_matrix"
    vcf = "vcf"
    de_table = "de_table"
    gsea_result = "gsea_result"
    splicing_table = "splicing_table"
    ucsc_track = "ucsc_track"
    html_report = "html_report"
    streamlit_data = "streamlit_data"
    scrna_h5ad = "scrna_h5ad"
    scrna_umap = "scrna_umap"
    marker_genes = "marker_genes"


class Executor(enum.StrEnum):
    local = "local"
    nextflow = "nextflow"
    aws_batch = "aws_batch"


class PassFail(enum.StrEnum):
    pass_ = "pass"
    warn = "warn"
    fail = "fail"


class SplicingEventType(enum.StrEnum):
    SE = "SE"
    A5SS = "A5SS"
    A3SS = "A3SS"
    MXE = "MXE"
    RI = "RI"


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"
    tool = "tool"


class ToolStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
