// GATK HaplotypeCaller variant calling module (requires @RG in the BAM — set by STAR_ALIGN)
process GATK_HAPLOTYPECALLER {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus params.threads
    memory params.memory

    input:
    tuple val(sample_id), path(bam), path(bai)
    tuple path(fasta), path(fai), path(dict)

    output:
    tuple val(sample_id), path("${sample_id}.raw.vcf.gz"), path("${sample_id}.raw.vcf.gz.tbi"), emit: vcf
    path "${sample_id}.gatk.version.txt", emit: version

    script:
    """
    gatk HaplotypeCaller -R ${fasta} -I ${bam} -O ${sample_id}.raw.vcf.gz \\
        --native-pair-hmm-threads ${task.cpus}
    gatk --version 2>/dev/null | grep -m1 -o 'v[0-9][0-9.]*' | sed 's/^v/GATK /' > ${sample_id}.gatk.version.txt
    """

    stub:
    """
    printf '##fileformat=VCFv4.2\\n#CHROM\\tPOS\\tID\\tREF\\tALT\\tQUAL\\tFILTER\\tINFO\\nchr1\\t100\\t.\\tA\\tG\\t50\\t.\\t.\\nchr1\\t200\\t.\\tC\\tT\\t50\\t.\\t.\\n' \\
        | gzip -c > ${sample_id}.raw.vcf.gz
    touch ${sample_id}.raw.vcf.gz.tbi
    echo 'GATK stub' > ${sample_id}.gatk.version.txt
    """
}

// GATK VariantFiltration hard filters (same expressions as the local VariantAgent)
process GATK_VARIANT_FILTER {
    tag "${sample_id}"
    publishDir params.output_dir, mode: 'copy'
    cpus 2
    memory params.memory

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

    stub:
    """
    printf '##fileformat=VCFv4.2\\n#CHROM\\tPOS\\tID\\tREF\\tALT\\tQUAL\\tFILTER\\tINFO\\nchr1\\t100\\t.\\tA\\tG\\t50\\tPASS\\t.\\nchr1\\t200\\t.\\tC\\tT\\t50\\tSNPFilter\\t.\\n' \\
        | gzip -c > ${sample_id}.filtered.vcf.gz
    touch ${sample_id}.filtered.vcf.gz.tbi
    """
}
