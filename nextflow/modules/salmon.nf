// Salmon quasi-mapping quantification module
process SALMON_QUANT {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory '16 GB'

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)
    path index

    output:
    tuple val(sample_id), path("${sample_id}"), emit: quant

    script:
    def reads = fastq_r2.name != 'NO_FILE' ? "-1 ${fastq_r1} -2 ${fastq_r2}" : "-r ${fastq_r1}"
    """
    salmon quant --index ${index} --libType A ${reads} \\
        --output ${sample_id} --threads ${task.cpus} --validateMappings
    """
}
