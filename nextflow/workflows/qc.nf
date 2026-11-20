// QC sub-workflow: FastQC for one sample
include { FASTQC } from '../modules/fastqc'

workflow QC_WORKFLOW {
    take:
    samples  // channel: [sample_id, fastq_r1, fastq_r2 | NO_FILE]

    main:
    FASTQC(samples)

    emit:
    html = FASTQC.out.html
    zip  = FASTQC.out.zip
}
