// samtools sort + index module
process SAMTOOLS_SORT_INDEX {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory params.memory

    input:
    tuple val(sample_id), path(bam)

    output:
    tuple val(sample_id), path("${sample_id}.sorted.bam"),     emit: bam
    tuple val(sample_id), path("${sample_id}.sorted.bam.bai"), emit: bai
    path "${sample_id}.samtools.version.txt",                  emit: version

    script:
    """
    samtools sort -@ ${task.cpus} -o ${sample_id}.sorted.bam ${bam}
    samtools index -@ ${task.cpus} ${sample_id}.sorted.bam
    samtools --version | head -n 1 > ${sample_id}.samtools.version.txt
    """

    stub:
    """
    touch ${sample_id}.sorted.bam ${sample_id}.sorted.bam.bai
    echo 'samtools stub' > ${sample_id}.samtools.version.txt
    """
}
