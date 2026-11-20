// STAR alignment module (unsorted-by-samtools BAM stays in the work dir)
process STAR_ALIGN {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy', pattern: "*{Log.final.out,SJ.out.tab,toTranscriptome.out.bam}"
    cpus params.threads
    memory '40 GB'

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)
    path genome_dir

    output:
    tuple val(sample_id), path("${sample_id}_Aligned.sortedByCoord.out.bam"), emit: bam
    tuple val(sample_id), path("${sample_id}_Log.final.out"),                 emit: log
    tuple val(sample_id), path("${sample_id}_SJ.out.tab"),                    emit: sj
    tuple val(sample_id), path("${sample_id}_Aligned.toTranscriptome.out.bam"), optional: true, emit: tx_bam

    script:
    def r2 = fastq_r2.name != 'NO_FILE' ? fastq_r2.toString() : ''
    def zcat = fastq_r1.name.endsWith('.gz') ? '--readFilesCommand zcat' : ''
    def quant = params.alignment_mode == 'genome' ? 'GeneCounts' : 'TranscriptomeSAM GeneCounts'
    """
    STAR \\
        --runMode alignReads \\
        --genomeDir ${genome_dir} \\
        --readFilesIn ${fastq_r1} ${r2} \\
        ${zcat} \\
        --outFileNamePrefix ${sample_id}_ \\
        --outSAMtype BAM SortedByCoordinate \\
        --quantMode ${quant} \\
        --runThreadN ${task.cpus}
    """
}
