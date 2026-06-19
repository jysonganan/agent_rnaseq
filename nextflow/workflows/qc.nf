// QC sub-workflow: FastQC on one or more samples
include { FASTQC } from '../modules/fastqc'

workflow QC_WORKFLOW {
    take:
    samples  // channel: [sample_id, fastq_r1, fastq_r2 (or null)]

    main:
    FASTQC(samples)

    emit:
    html = FASTQC.out.html
    zip  = FASTQC.out.zip
}
