// Quantification sub-workflow: HTSeq-count (default)
// Additional modes (salmon, rsem) are selected via params.quant_mode
include { HTSEQ_COUNT            } from '../modules/htseq'
include { SALMON_QUANT           } from '../modules/salmon'
include { RSEM_CALCULATE_EXPRESSION } from '../modules/rsem'

workflow QUANTIFICATION_WORKFLOW {
    take:
    samples   // channel: [sample_id, bam_or_fastq_r1, fastq_r2]
    gtf       // path: gene annotation GTF (for HTSeq)

    main:
    def mode = params.quant_mode ?: 'star_htseq'

    if (mode == 'star_htseq') {
        HTSEQ_COUNT(samples, gtf)
        counts = HTSEQ_COUNT.out.counts
    } else if (mode == 'salmon') {
        def idx = file(params.salmon_index ?: '.')
        SALMON_QUANT(samples, idx)
        counts = SALMON_QUANT.out.quant
    } else if (mode == 'rsem') {
        def ref = file(params.rsem_reference ?: '.')
        RSEM_CALCULATE_EXPRESSION(samples, ref)
        counts = RSEM_CALCULATE_EXPRESSION.out.genes
    } else {
        error "Unknown quant_mode '${mode}'. Choose: star_htseq, salmon, rsem"
    }

    emit:
    counts = counts
}
