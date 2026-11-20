#!/usr/bin/env nextflow
nextflow.enable.dsl = 2

// Invoked once per stage and sample by the agent's Nextflow backend
// (src/tools/nextflow/stage_runner.py). Results are published to --output_dir.

if (params.help) {
    log.info """
RNA-seq Agent Pipeline
======================
Usage:
  nextflow run main.nf -profile <local|awsbatch> --workflow <name> --sample_id <id> --output_dir <dir> [options]

Workflows and their parameters:
  qc               --fastq_r1 [--fastq_r2]
  alignment        --fastq_r1 [--fastq_r2] --genome_dir [--alignment_mode genome|transcriptome|both]
  quantification   --quant_mode star_htseq --bam --gtf_path
                   --quant_mode salmon     --fastq_r1 [--fastq_r2] --salmon_index
                   --quant_mode rsem       --bam --rsem_reference <index prefix>
  variant_calling  --bam --bai --reference_fasta   (.fai and .dict must sit next to the FASTA)

Common: --threads, --tools_image (container with pinned tool versions)
""".stripIndent()
    exit 0
}

include { QC_WORKFLOW              } from './workflows/qc'
include { ALIGNMENT_WORKFLOW       } from './workflows/alignment'
include { QUANTIFICATION_WORKFLOW  } from './workflows/quantification'
include { VARIANT_CALLING_WORKFLOW } from './workflows/variant_calling'

def NO_FILE = file("${projectDir}/assets/NO_FILE")

def required(name) {
    if (!params[name]) error "--${name} is required for --workflow ${params.workflow}"
    return file(params[name], checkIfExists: true)
}

def optionalFile(name) {
    return params[name] ? file(params[name], checkIfExists: true) : NO_FILE
}

def readsChannel() {
    return Channel.of(tuple(params.sample_id, required('fastq_r1'), optionalFile('fastq_r2')))
}

workflow {
    switch (params.workflow) {
        case 'qc':
            QC_WORKFLOW(readsChannel())
            break

        case 'alignment':
            ALIGNMENT_WORKFLOW(readsChannel(), required('genome_dir'))
            break

        case 'quantification':
            if (params.quant_mode == 'salmon') {
                QUANTIFICATION_WORKFLOW(readsChannel(), NO_FILE, required('salmon_index'), NO_FILE)
            } else if (params.quant_mode == 'rsem') {
                // rsem_reference is an index prefix: stage its directory, pass the basename
                def prefix = params.rsem_reference
                if (!prefix) error "--rsem_reference is required for --quant_mode rsem"
                def cut = prefix.lastIndexOf('/')
                def rsemDir = file(prefix.substring(0, cut), checkIfExists: true)
                QUANTIFICATION_WORKFLOW(
                    Channel.of(tuple(params.sample_id, required('bam'))),
                    NO_FILE, NO_FILE, tuple(rsemDir, prefix.substring(cut + 1))
                )
            } else {
                QUANTIFICATION_WORKFLOW(
                    Channel.of(tuple(params.sample_id, required('bam'))),
                    required('gtf_path'), NO_FILE, NO_FILE
                )
            }
            break

        case 'variant_calling':
            def fasta = params.reference_fasta
            if (!fasta) error "--reference_fasta is required for --workflow variant_calling"
            def dict = fasta.replaceAll(/\.(fa|fasta|fna)$/, '') + '.dict'
            def ref = tuple(
                file(fasta, checkIfExists: true),
                file("${fasta}.fai", checkIfExists: true),
                file(dict, checkIfExists: true)
            )
            VARIANT_CALLING_WORKFLOW(
                Channel.of(tuple(params.sample_id, required('bam'), required('bai'))), ref
            )
            break

        default:
            error "Unknown --workflow '${params.workflow}'. Choose: qc, alignment, quantification, variant_calling"
    }
}
