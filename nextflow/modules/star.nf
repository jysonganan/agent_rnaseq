// STAR alignment module
process STAR_ALIGN {
    tag "${sample_id}"
    container 'biocontainers/star:2.7.10a--h9ee0642_0'
    cpus 8
    memory '40 GB'

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)
    path genome_dir

    output:
    tuple val(sample_id), path("${sample_id}_Aligned.sortedByCoord.out.bam"), emit: bam
    tuple val(sample_id), path("${sample_id}_Log.final.out"),                 emit: log
    tuple val(sample_id), path("${sample_id}_SJ.out.tab"),                    emit: sj

    script:
    def r2_arg = fastq_r2 ? fastq_r2.toString() : ''
    """
    STAR \
        --runMode alignReads \
        --genomeDir ${genome_dir} \
        --readFilesIn ${fastq_r1} ${r2_arg} \
        --outFileNamePrefix ${sample_id}_ \
        --outSAMtype BAM SortedByCoordinate \
        --quantMode GeneCounts \
        --runThreadN ${task.cpus} \
        --outSAMattributes NH HI AS NM MD \
        --readFilesCommand zcat
    """
}
