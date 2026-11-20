// RSEM gene/isoform quantification module (input: STAR transcriptome BAM)
process RSEM_CALCULATE_EXPRESSION {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory params.memory

    input:
    tuple val(sample_id), path(bam)
    tuple path(rsem_dir), val(rsem_prefix)

    output:
    tuple val(sample_id), path("${sample_id}.genes.results"),    emit: genes
    tuple val(sample_id), path("${sample_id}.isoforms.results"), emit: isoforms
    tuple val(sample_id), path("${sample_id}.stat"),             emit: stat
    path "${sample_id}.rsem.version.txt",                        emit: version

    script:
    """
    rsem-calculate-expression --bam --paired-end --no-bam-output \\
        --num-threads ${task.cpus} ${bam} ${rsem_dir}/${rsem_prefix} ${sample_id}
    rsem-calculate-expression --version | sed 's/^Current version: //' > ${sample_id}.rsem.version.txt
    """

    stub:
    """
    mkdir -p ${sample_id}.stat
    printf 'gene_id\\ttranscript_id(s)\\tlength\\teffective_length\\texpected_count\\tTPM\\tFPKM\\nGENE_A\\tTX_A\\t1000\\t800\\t42.00\\t10.0\\t5.0\\n' > ${sample_id}.genes.results
    cp ${sample_id}.genes.results ${sample_id}.isoforms.results
    echo 'RSEM stub' > ${sample_id}.rsem.version.txt
    """
}
