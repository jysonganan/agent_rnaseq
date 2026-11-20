// HTSeq-count gene quantification module
process HTSEQ_COUNT {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus 1
    memory '8 GB'

    input:
    tuple val(sample_id), path(bam)
    path gtf

    output:
    tuple val(sample_id), path("${sample_id}_counts.tsv"), emit: counts

    script:
    """
    htseq-count --format bam --order pos --stranded reverse --mode union \\
        ${bam} ${gtf} > ${sample_id}_counts.tsv
    """
}
