// Alignment sub-workflow: STAR align → samtools sort/index
include { STAR_ALIGN         } from '../modules/star'
include { SAMTOOLS_SORT_INDEX } from '../modules/samtools'

workflow ALIGNMENT_WORKFLOW {
    take:
    samples     // channel: [sample_id, fastq_r1, fastq_r2]
    genome_dir  // path: STAR genome index

    main:
    STAR_ALIGN(samples, genome_dir)
    SAMTOOLS_SORT_INDEX(STAR_ALIGN.out.bam)

    emit:
    bam     = SAMTOOLS_SORT_INDEX.out.bam
    bai     = SAMTOOLS_SORT_INDEX.out.bai
    star_log = STAR_ALIGN.out.log
}
