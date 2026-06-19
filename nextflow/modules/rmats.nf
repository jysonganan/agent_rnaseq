// rMATS differential splicing analysis module
process RMATS {
    tag "${contrast}"
    container 'xinglab/rmats-turbo:v4.1.2'
    cpus 8
    memory '32 GB'

    input:
    val  contrast
    path bam_list_b1  // file listing BAM paths for condition 1
    path bam_list_b2  // file listing BAM paths for condition 2
    path gtf
    val  read_length

    output:
    tuple val(contrast), path("${contrast}/"), emit: results

    script:
    """
    python /rmats/rmats.py \
        --b1 ${bam_list_b1} \
        --b2 ${bam_list_b2} \
        --gtf ${gtf} \
        --od ${contrast} \
        --tmp ${contrast}_tmp \
        -t paired \
        --readLength ${read_length} \
        --nthread ${task.cpus} \
        --statoff
    """
}
