// STAR alignment module (the STAR-sorted BAM stays in the work dir; samtools output is published)
process STAR_ALIGN {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy', pattern: "*{Log.final.out,SJ.out.tab,toTranscriptome.out.bam,version.txt}"
    cpus params.threads
    memory params.memory

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)
    path genome_dir

    output:
    tuple val(sample_id), path("${sample_id}_Aligned.sortedByCoord.out.bam"), emit: bam
    tuple val(sample_id), path("${sample_id}_Log.final.out"),                 emit: log
    tuple val(sample_id), path("${sample_id}_SJ.out.tab"),                    emit: sj
    tuple val(sample_id), path("${sample_id}_Aligned.toTranscriptome.out.bam"), optional: true, emit: tx_bam
    path "${sample_id}.star.version.txt",                                     emit: version

    script:
    def r2 = fastq_r2.name != 'NO_FILE' ? fastq_r2.toString() : ''
    def zcat = fastq_r1.name.endsWith('.gz') ? '--readFilesCommand zcat' : ''
    def quant = params.alignment_mode == 'genome' ? 'GeneCounts' : 'TranscriptomeSAM GeneCounts'
    def rg = params.read_group ?: sample_id
    """
    STAR \\
        --runMode alignReads \\
        --genomeDir ${genome_dir} \\
        --readFilesIn ${fastq_r1} ${r2} \\
        ${zcat} \\
        --outFileNamePrefix ${sample_id}_ \\
        --outSAMtype BAM SortedByCoordinate \\
        --outSAMattrRGline ID:${rg} SM:${rg} PL:ILLUMINA \\
        --quantMode ${quant} \\
        --runThreadN ${task.cpus}
    echo "STAR \$(STAR --version)" > ${sample_id}.star.version.txt
    """

    stub:
    def tx = params.alignment_mode == 'genome' ? '' : "touch ${sample_id}_Aligned.toTranscriptome.out.bam"
    """
    touch ${sample_id}_Aligned.sortedByCoord.out.bam ${sample_id}_SJ.out.tab
    ${tx}
    cat > ${sample_id}_Log.final.out <<'LOG'
                          Number of input reads |	1000
                        Uniquely mapped reads % |	90.00%
             % of reads mapped to multiple loci |	5.00%
                 % of reads unmapped: too short |	5.00%
LOG
    echo 'STAR stub' > ${sample_id}.star.version.txt
    """
}
