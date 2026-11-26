// Post-alignment QC sub-workflow: RSeQC on the sorted BAM
include { RSEQC } from '../modules/rseqc'

workflow ALIGNMENT_QC_WORKFLOW {
    take:
    samples  // channel: [sample_id, bam, bai]
    bed      // path: BED12 gene model

    main:
    RSEQC(samples, bed)

    emit:
    read_distribution = RSEQC.out.read_distribution
    infer_experiment  = RSEQC.out.infer_experiment
}
