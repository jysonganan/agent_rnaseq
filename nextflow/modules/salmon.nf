// Salmon quasi-mapping quantification module
process SALMON_QUANT {
    tag "${sample_id}"
    container 'combinelab/salmon:1.10.0'
    cpus 8
    memory '16 GB'

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)
    path index

    output:
    tuple val(sample_id), path("${sample_id}/quant.sf"),          emit: quant
    tuple val(sample_id), path("${sample_id}/aux_info/meta_info.json"), emit: meta

    script:
    def reads = fastq_r2 ? "-1 ${fastq_r1} -2 ${fastq_r2}" : "-r ${fastq_r1}"
    """
    salmon quant \
        --index ${index} \
        --libType A \
        ${reads} \
        --output ${sample_id} \
        --threads ${task.cpus} \
        --validateMappings
    """
}
