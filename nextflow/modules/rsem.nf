// RSEM gene/isoform quantification module
process RSEM_CALCULATE_EXPRESSION {
    tag "${sample_id}"
    container 'biocontainers/rsem:1.3.3--pl5321h9f5acd7_3'
    cpus 8
    memory '16 GB'

    input:
    tuple val(sample_id), path(bam)
    path rsem_reference

    output:
    tuple val(sample_id), path("${sample_id}.genes.results"),    emit: genes
    tuple val(sample_id), path("${sample_id}.isoforms.results"), emit: isoforms

    script:
    """
    rsem-calculate-expression \
        --bam \
        --paired-end \
        --no-bam-output \
        --num-threads ${task.cpus} \
        ${bam} \
        ${rsem_reference}/rsem_ref \
        ${sample_id}
    """
}
