// HTSeq-count gene quantification module (dUTP / reverse-stranded libraries)
process HTSEQ_COUNT {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus 1
    memory params.memory

    input:
    tuple val(sample_id), path(bam)
    path gtf

    output:
    tuple val(sample_id), path("${sample_id}_counts.tsv"), emit: counts
    path "${sample_id}.htseq.version.txt",                 emit: version

    script:
    """
    htseq-count --format bam --order pos --stranded reverse --mode union \\
        ${bam} ${gtf} > ${sample_id}_counts.tsv
    echo "HTSeq \$(htseq-count --version)" > ${sample_id}.htseq.version.txt
    """

    stub:
    """
    printf 'GENE_A\\t10\\nGENE_B\\t20\\n__no_feature\\t3\\n__ambiguous\\t1\\n' > ${sample_id}_counts.tsv
    echo 'HTSeq stub' > ${sample_id}.htseq.version.txt
    """
}
