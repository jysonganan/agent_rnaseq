// samtools sort + index module
process SAMTOOLS_SORT_INDEX {
    tag "${sample_id}"
    container 'biocontainers/samtools:1.17--h00cdaf9_0'
    cpus 4
    memory '8 GB'

    input:
    tuple val(sample_id), path(bam)

    output:
    tuple val(sample_id), path("${sample_id}.sorted.bam"),     emit: bam
    tuple val(sample_id), path("${sample_id}.sorted.bam.bai"), emit: bai

    script:
    """
    samtools sort \
        -@ ${task.cpus} \
        -o ${sample_id}.sorted.bam \
        ${bam}

    samtools index \
        -@ ${task.cpus} \
        ${sample_id}.sorted.bam
    """
}
