// RSeQC post-alignment QC module: read distribution + strandedness (infer_experiment)
process RSEQC {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus 1
    memory params.memory

    input:
    tuple val(sample_id), path(bam), path(bai)
    path bed

    output:
    tuple val(sample_id), path("${sample_id}.rseqc_read_distribution.txt"), emit: read_distribution
    tuple val(sample_id), path("${sample_id}.rseqc_infer_experiment.txt"),  emit: infer_experiment
    path "${sample_id}.rseqc.version.txt",                                  emit: version

    script:
    """
    read_distribution.py -i ${bam} -r ${bed} > ${sample_id}.rseqc_read_distribution.txt
    infer_experiment.py -i ${bam} -r ${bed} > ${sample_id}.rseqc_infer_experiment.txt
    read_distribution.py --version 2>&1 | head -n 1 > ${sample_id}.rseqc.version.txt
    """

    stub:
    """
    printf 'Total Reads                   1000\\nTotal Tags                    1000\\nTotal Assigned Tags           900\\n' \\
        > ${sample_id}.rseqc_read_distribution.txt
    printf 'Group               Total_bases         Tag_count           Tags/Kb\\n' \\
        >> ${sample_id}.rseqc_read_distribution.txt
    printf 'CDS_Exons           1000                800                 800.00\\n' \\
        >> ${sample_id}.rseqc_read_distribution.txt
    printf 'This is PairEnd Data\\nFraction of reads failed to determine: 0.0100\\n' \\
        > ${sample_id}.rseqc_infer_experiment.txt
    printf 'Fraction of reads explained by "1++,1--,2+-,2-+": 0.0100\\n' \\
        >> ${sample_id}.rseqc_infer_experiment.txt
    printf 'Fraction of reads explained by "1+-,1-+,2++,2--": 0.9800\\n' \\
        >> ${sample_id}.rseqc_infer_experiment.txt
    echo 'RSeQC stub' > ${sample_id}.rseqc.version.txt
    """
}
