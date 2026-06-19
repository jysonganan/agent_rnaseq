// HTSeq-count gene quantification module
process HTSEQ_COUNT {
    tag "${sample_id}"
    container 'biocontainers/htseq:2.0.2--py310h4b6aa87_0'
    cpus 4
    memory '8 GB'

    input:
    tuple val(sample_id), path(bam)
    path gtf

    output:
    tuple val(sample_id), path("${sample_id}_counts.tsv"), emit: counts

    script:
    """
    htseq-count \
        --format bam \
        --order pos \
        --stranded reverse \
        --mode union \
        --quiet \
        ${bam} \
        ${gtf} \
        > ${sample_id}_counts.tsv
    """
}
