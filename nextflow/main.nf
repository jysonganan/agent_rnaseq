#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

// ── Help ──────────────────────────────────────────────────────────────────────
if (params.help) {
    log.info """
RNA-seq Agent Pipeline
======================
Usage:
  nextflow run main.nf [options]

Options:
  --workflow         Pipeline to run: qc | alignment | quantification | variant_calling
  --sample_id        Sample identifier (default: sample)
  --fastq_r1         Path to R1 FASTQ (local or s3://)
  --fastq_r2         Path to R2 FASTQ (optional; omit for single-end)
  --genome_dir       STAR genome index directory
  --gtf_path         Gene annotation GTF file
  --output_dir       Output directory (default: ./results)
  --threads          CPU threads per process (default: 8)
  --help             Show this message and exit

Profiles:
  -profile local     Run locally (default)
  -profile awsbatch  Run on AWS Batch
""".stripIndent()
    exit 0
}

// ── Workflow imports ──────────────────────────────────────────────────────────
include { QC_WORKFLOW            } from './workflows/qc'
include { ALIGNMENT_WORKFLOW     } from './workflows/alignment'
include { QUANTIFICATION_WORKFLOW} from './workflows/quantification'
include { VARIANT_CALLING_WORKFLOW} from './workflows/variant_calling'

// ── Entry workflow ────────────────────────────────────────────────────────────
workflow {

    // Build a samples channel: [sample_id, fastq_r1, fastq_r2 (or null)]
    def r2 = params.fastq_r2 ? file(params.fastq_r2) : null
    def samples = Channel.of(
        tuple(params.sample_id, file(params.fastq_r1 ?: '/dev/null'), r2)
    )

    switch (params.workflow) {
        case 'qc':
            QC_WORKFLOW(samples)
            break
        case 'alignment':
            ALIGNMENT_WORKFLOW(samples, file(params.genome_dir ?: '.'))
            break
        case 'quantification':
            // Expects pre-aligned BAM; reuse samples channel as bam channel
            QUANTIFICATION_WORKFLOW(samples, file(params.gtf_path ?: '.'))
            break
        case 'variant_calling':
            VARIANT_CALLING_WORKFLOW(samples, file(params.genome_dir ?: '.'))
            break
        default:
            error "Unknown --workflow '${params.workflow}'. Choose: qc, alignment, quantification, variant_calling"
    }
}
