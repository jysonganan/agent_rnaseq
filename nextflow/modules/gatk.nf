// GATK HaplotypeCaller variant calling module
process GATK_HAPLOTYPECALLER {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory '16 GB'

    input:
    tuple val(sample_id), path(bam), path(bai)
    tuple path(fasta), path(fai), path(dict)

    output:
    tuple val(sample_id), path("${sample_id}.raw.vcf.gz"), path("${sample_id}.raw.vcf.gz.tbi"), emit: vcf

    script:
    """
    gatk HaplotypeCaller -R ${fasta} -I ${bam} -O ${sample_id}.raw.vcf.gz \\
        --native-pair-hmm-threads ${task.cpus}
    """
}

// GATK VariantFiltration hard filters (same expressions as the local VariantAgent)
process GATK_VARIANT_FILTER {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus 2
    memory '8 GB'

    input:
    tuple val(sample_id), path(vcf), path(tbi)
    tuple path(fasta), path(fai), path(dict)

    output:
    tuple val(sample_id), path("${sample_id}.filtered.vcf.gz"), path("${sample_id}.filtered.vcf.gz.tbi"), emit: vcf

    script:
    """
    gatk VariantFiltration -R ${fasta} -V ${vcf} -O ${sample_id}.filtered.vcf.gz \\
        --filter-expression "${params.snp_filter}" --filter-name SNPFilter \\
        --filter-expression "${params.indel_filter}" --filter-name IndelFilter
    """
}
