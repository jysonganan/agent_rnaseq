// samtools sort + index module
process SAMTOOLS_SORT_INDEX {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory '8 GB'

    input:
    tuple val(sample_id), path(bam)

    output:
    tuple val(sample_id), path("${sample_id}.sorted.bam"),     emit: bam
    tuple val(sample_id), path("${sample_id}.sorted.bam.bai"), emit: bai

    script:
    """
    samtools sort -@ ${task.cpus} -o ${sample_id}.sorted.bam ${bam}
    samtools index -@ ${task.cpus} ${sample_id}.sorted.bam
    """
}
