// FastQC quality control module
process FASTQC {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory params.memory

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)

    output:
    tuple val(sample_id), path("*_fastqc.html"), emit: html
    tuple val(sample_id), path("*_fastqc.zip"),  emit: zip
    path "${sample_id}.fastqc.version.txt",      emit: version

    script:
    def reads = fastq_r2.name != 'NO_FILE' ? "${fastq_r1} ${fastq_r2}" : "${fastq_r1}"
    """
    fastqc ${reads} --threads ${task.cpus} --outdir .
    fastqc --version | head -n 1 > ${sample_id}.fastqc.version.txt
    """

    stub:
    def fqs = [fastq_r1] + (fastq_r2.name != 'NO_FILE' ? [fastq_r2] : [])
    def stems = fqs.collect { it.name.replaceAll(/\.(fastq|fq)(\.gz)?$/, '') }.join(' ')
    """
    for stem in ${stems}; do
        mkdir -p "\${stem}_fastqc"
        printf 'PASS\\tBasic Statistics\\t%s\\nWARN\\tPer sequence GC content\\t%s\\n' "\$stem" "\$stem" \\
            > "\${stem}_fastqc/summary.txt"
        zip -qr "\${stem}_fastqc.zip" "\${stem}_fastqc"
        echo '<html>stub</html>' > "\${stem}_fastqc.html"
    done
    echo 'FastQC stub' > ${sample_id}.fastqc.version.txt
    """
}
