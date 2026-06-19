// FastQC quality control module
process FASTQC {
    tag "${sample_id}"
    container 'biocontainers/fastqc:0.11.9--0'
    cpus 4
    memory '8 GB'

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)

    output:
    tuple val(sample_id), path("*.html"), emit: html
    tuple val(sample_id), path("*.zip"),  emit: zip

    script:
    def reads = fastq_r2 ? "${fastq_r1} ${fastq_r2}" : "${fastq_r1}"
    """
    fastqc ${reads} \
        --threads ${task.cpus} \
        --outdir .
    """
}
