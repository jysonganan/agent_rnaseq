// Quantification sub-workflow; mode selected by params.quant_mode
include { HTSEQ_COUNT               } from '../modules/htseq'
include { SALMON_QUANT              } from '../modules/salmon'
include { RSEM_CALCULATE_EXPRESSION } from '../modules/rsem'

workflow QUANTIFICATION_WORKFLOW {
    take:
    samples       // star_htseq/rsem: [sample_id, bam]; salmon: [sample_id, fastq_r1, fastq_r2]
    gtf           // star_htseq only (else NO_FILE)
    salmon_index  // salmon only (else NO_FILE)
    rsem_ref      // rsem only: [index_dir, prefix] (else NO_FILE)

    main:
    def mode = params.quant_mode ?: 'star_htseq'
    if (mode == 'star_htseq') {
        HTSEQ_COUNT(samples, gtf)
        counts = HTSEQ_COUNT.out.counts
    } else if (mode == 'salmon') {
        SALMON_QUANT(samples, salmon_index)
        counts = SALMON_QUANT.out.quant
    } else if (mode == 'rsem') {
        RSEM_CALCULATE_EXPRESSION(samples, rsem_ref)
        counts = RSEM_CALCULATE_EXPRESSION.out.genes
    } else {
        error "Unknown quant_mode '${mode}'. Choose: star_htseq, salmon, rsem"
    }

    emit:
    counts = counts
}
