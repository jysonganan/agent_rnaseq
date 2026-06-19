# Demo Data

Synthetic paired-end bulk RNA-seq FASTQ files for running the `agent_rnaseq` demo notebook.

## Experiment design

| File | Sample | Condition | Replicate |
|---|---|---|---|
| `ctrl_1_R1.fastq.gz` / `ctrl_1_R2.fastq.gz` | ctrl_1 | control | 1 |
| `ctrl_2_R1.fastq.gz` / `ctrl_2_R2.fastq.gz` | ctrl_2 | control | 2 |
| `treat_1_R1.fastq.gz` / `treat_1_R2.fastq.gz` | treat_1 | treatment | 1 |
| `treat_2_R1.fastq.gz` / `treat_2_R2.fastq.gz` | treat_2 | treatment | 2 |

## Specifications

- 2 000 read pairs per sample
- 100 bp read length
- Paired-end (R1 + R2)
- Illumina-style Phred+33 quality scores (Q20–Q40)
- Treatment samples have slightly elevated GC content (55 % vs 50 %) to simulate real composition differences
- Random sequences — **not from any real organism** — sufficient for dry-run pipeline demo

## Regenerate

```bash
python data/generate_data.py
```

## Note on TCGA data

Real TCGA data requires controlled access through the NIH dbGaP portal
(https://www.ncbi.nlm.nih.gov/gap/) and appropriate data use agreements.
The synthetic files above are suitable for pipeline demonstration purposes.
For real analysis, replace these paths with your approved FASTQ files.
