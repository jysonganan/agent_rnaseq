// FastQC quality control module
process FASTQC {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory '8 GB'

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)

    output:
    tuple val(sample_id), path("*_fastqc.html"), emit: html
    tuple val(sample_id), path("*_fastqc.zip"),  emit: zip

    script:
    def reads = fastq_r2.name != 'NO_FILE' ? "${fastq_r1} ${fastq_r2}" : "${fastq_r1}"
    """
    fastqc ${reads} --threads ${task.cpus} --outdir .
    """
}
