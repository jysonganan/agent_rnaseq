// Variant calling sub-workflow: GATK HaplotypeCaller → VariantFiltration
include { GATK_HAPLOTYPECALLER } from '../modules/gatk'
include { GATK_VARIANT_FILTER  } from '../modules/gatk'

workflow VARIANT_CALLING_WORKFLOW {
    take:
    samples    // channel: [sample_id, bam, bai]
    reference  // tuple: [fasta, fai, dict]

    main:
    GATK_HAPLOTYPECALLER(samples, reference)
    GATK_VARIANT_FILTER(GATK_HAPLOTYPECALLER.out.vcf, reference)

    emit:
    vcf = GATK_VARIANT_FILTER.out.vcf
}
