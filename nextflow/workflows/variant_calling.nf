// Variant calling sub-workflow: GATK HaplotypeCaller → VariantFiltration
include { GATK_HAPLOTYPECALLER } from '../modules/gatk'
include { GATK_VARIANT_FILTER  } from '../modules/gatk'

workflow VARIANT_CALLING_WORKFLOW {
    take:
    samples      // channel: [sample_id, bam, bai]
    genome_dir   // path: directory containing reference.fa (and .dict/.fai)

    main:
    def ref = file("${genome_dir}/reference.fa")
    GATK_HAPLOTYPECALLER(samples, ref)
    GATK_VARIANT_FILTER(GATK_HAPLOTYPECALLER.out.vcf.join(GATK_HAPLOTYPECALLER.out.tbi), ref)

    emit:
    vcf = GATK_VARIANT_FILTER.out.vcf
    tbi = GATK_VARIANT_FILTER.out.tbi
}
