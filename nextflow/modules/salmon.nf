// Salmon quasi-mapping quantification module
process SALMON_QUANT {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory params.memory

    input:
    tuple val(sample_id), path(fastq_r1), path(fastq_r2)
    path index

    output:
    tuple val(sample_id), path("${sample_id}"), emit: quant
    path "${sample_id}.salmon.version.txt",     emit: version

    script:
    def reads = fastq_r2.name != 'NO_FILE' ? "-1 ${fastq_r1} -2 ${fastq_r2}" : "-r ${fastq_r1}"
    """
    salmon quant --index ${index} --libType A ${reads} \\
        --output ${sample_id} --threads ${task.cpus} --validateMappings
    salmon --version > ${sample_id}.salmon.version.txt
    """

    stub:
    """
    mkdir -p ${sample_id}/aux_info
    printf 'Name\\tLength\\tEffectiveLength\\tTPM\\tNumReads\\nTX_A\\t1000\\t800\\t10.0\\t42.0\\n' > ${sample_id}/quant.sf
    echo '{"mapping_rate": 0.9}' > ${sample_id}/lib_format_counts.json
    echo '{"percent_mapped": 90.0, "library_types": ["ISR"]}' > ${sample_id}/aux_info/meta_info.json
    echo 'salmon stub' > ${sample_id}.salmon.version.txt
    """
}
