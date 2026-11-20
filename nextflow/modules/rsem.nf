// RSEM gene/isoform quantification module (input: STAR transcriptome BAM)
process RSEM_CALCULATE_EXPRESSION {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory '16 GB'

    input:
    tuple val(sample_id), path(bam)
    tuple path(rsem_dir), val(rsem_prefix)

    output:
    tuple val(sample_id), path("${sample_id}.genes.results"),    emit: genes
    tuple val(sample_id), path("${sample_id}.isoforms.results"), emit: isoforms
    tuple val(sample_id), path("${sample_id}.stat"),             emit: stat

    script:
    """
    rsem-calculate-expression --bam --paired-end --no-bam-output \\
        --num-threads ${task.cpus} ${bam} ${rsem_dir}/${rsem_prefix} ${sample_id}
    """
}
