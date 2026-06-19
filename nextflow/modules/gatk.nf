// GATK HaplotypeCaller variant calling module
process GATK_HAPLOTYPECALLER {
    tag "${sample_id}"
    container 'broadinstitute/gatk:4.4.0.0'
    cpus 4
    memory '16 GB'

    input:
    tuple val(sample_id), path(bam), path(bai)
    path reference_fasta

    output:
    tuple val(sample_id), path("${sample_id}.raw.vcf.gz"),     emit: vcf
    tuple val(sample_id), path("${sample_id}.raw.vcf.gz.tbi"), emit: tbi

    script:
    """
    gatk HaplotypeCaller \
        -R ${reference_fasta} \
        -I ${bam} \
        -O ${sample_id}.raw.vcf.gz \
        --native-pair-hmm-threads ${task.cpus}
    """
}

// GATK VariantFiltration hard-filter module
process GATK_VARIANT_FILTER {
    tag "${sample_id}"
    container 'broadinstitute/gatk:4.4.0.0'
    cpus 2
    memory '8 GB'

    input:
    tuple val(sample_id), path(vcf), path(tbi)
    path reference_fasta

    output:
    tuple val(sample_id), path("${sample_id}.filtered.vcf.gz"),     emit: vcf
    tuple val(sample_id), path("${sample_id}.filtered.vcf.gz.tbi"), emit: tbi

    script:
    """
    gatk VariantFiltration \
        -R ${reference_fasta} \
        -V ${vcf} \
        --filter-expression "QD < 2.0 || FS > 60.0 || MQ < 40.0" \
        --filter-name "LowQuality" \
        -O ${sample_id}.filtered.vcf.gz
    """
}
