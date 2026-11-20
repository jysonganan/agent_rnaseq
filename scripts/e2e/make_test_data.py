#!/usr/bin/env python3
"""Generate a tiny, alignable RNA-seq dataset with a known answer for end-to-end tests.

Output (``--out``, default ``e2e_data/``)::

    reference/genome.fa        one chromosome (``chr1``), a few dozen kb
    reference/genes.gtf        two-exon genes on both strands (gene/transcript/exon rows)
    fastq/<sample>_R{1,2}.fq.gz paired-end, reverse-stranded (dUTP) reads
    samples.tsv                name, condition, fastq_r1, fastq_r2
    truth.json                 DE genes (up/down), planted SNPs, contrast, read length

Design: 3 ``control`` + 3 ``treated`` samples; ``N_UP`` genes are 4x higher and ``N_DOWN``
genes 4x lower in ``treated``; 3 homozygous exonic SNPs are present in every sample's reads.
Pure Python and deterministic (``--seed``) so it runs anywhere, including CI.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from pathlib import Path

N_GENES = 24
N_UP = 4
N_DOWN = 4
FOLD = 4.0
READ_LEN = 75
FRAG_MEAN, FRAG_SD = 220, 25
EXON1, INTRON, EXON2, GAP = 400, 250, 600, 300
ERROR_RATE = 0.002
SAMPLES = [(f"ctrl_{i}", "control") for i in (1, 2, 3)] + [
    (f"treat_{i}", "treated") for i in (1, 2, 3)
]
_COMP = str.maketrans("ACGT", "TGCA")


def revcomp(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _random_seq(rng: random.Random, n: int) -> str:
    return "".join(rng.choices("ACGT", weights=[0.27, 0.23, 0.23, 0.27], k=n))


def _poisson(rng: random.Random, lam: float) -> int:
    """Overdispersed count (gamma-Poisson approximated by a normal for these lambdas)."""
    lam = rng.gammavariate(20.0, lam / 20.0)  # biological variation (dispersion 0.05)
    return max(0, round(rng.gauss(lam, math.sqrt(lam))))


def build_genome(rng: random.Random) -> tuple[str, list[dict]]:
    genes, parts, pos = [], [], 0
    parts.append(_random_seq(rng, GAP))
    pos += GAP
    for i in range(N_GENES):
        start = pos + 1  # 1-based
        e1 = (start, start + EXON1 - 1)
        e2 = (e1[1] + INTRON + 1, e1[1] + INTRON + EXON2)
        # canonical GT..AG intron so STAR can call the junction
        intron = "GT" + _random_seq(rng, INTRON - 4) + "AG"
        parts += [_random_seq(rng, EXON1), intron, _random_seq(rng, EXON2), _random_seq(rng, GAP)]
        pos = e2[1] + GAP
        genes.append(
            {
                "gene_id": f"GENE{i + 1:03d}",
                "strand": "+" if i % 2 == 0 else "-",
                "exons": [e1, e2],
                "base_mean": rng.randint(300, 900),
            }
        )
    return "".join(parts), genes


def transcript_seq(genome: str, gene: dict) -> str:
    seq = "".join(genome[a - 1 : b] for a, b in gene["exons"])
    return seq if gene["strand"] == "+" else revcomp(seq)


def tx_to_genome(gene: dict, tx_pos: int) -> int:
    """1-based genomic coordinate of 0-based transcript position."""
    (a1, b1), (a2, b2) = gene["exons"]
    len1, total = b1 - a1 + 1, (b1 - a1 + 1) + (b2 - a2 + 1)
    p = tx_pos if gene["strand"] == "+" else total - 1 - tx_pos
    return a1 + p if p < len1 else a2 + (p - len1)


def plant_snps(rng: random.Random, genome: str, genes: list[dict]) -> tuple[str, list[dict]]:
    g = list(genome)
    snps = []
    for gene in sorted(genes, key=lambda x: -x["base_mean"])[:3]:
        a, b = gene["exons"][1]
        pos = rng.randint(a + 100, b - 100)  # well inside exon 2, away from the junction
        ref = g[pos - 1]
        alt = rng.choice([c for c in "ACGT" if c != ref])
        g[pos - 1] = alt
        snps.append({"chrom": "chr1", "pos": pos, "ref": ref, "alt": alt, "gene": gene["gene_id"]})
    return "".join(g), snps


def _mutate(rng: random.Random, read: str) -> str:
    return "".join(
        rng.choice([c for c in "ACGT" if c != b]) if rng.random() < ERROR_RATE else b for b in read
    )


def simulate_sample(
    rng: random.Random, tx_seqs: dict[str, str], counts: dict[str, int], out_dir: Path, name: str
) -> tuple[str, str]:
    r1_path, r2_path = out_dir / f"{name}_R1.fq.gz", out_dir / f"{name}_R2.fq.gz"
    qual = "I" * READ_LEN
    n = 0
    with gzip.open(r1_path, "wt") as r1, gzip.open(r2_path, "wt") as r2:
        for gene_id, k in counts.items():
            tx = tx_seqs[gene_id]
            for _ in range(k):
                flen = min(len(tx), max(READ_LEN + 10, round(rng.gauss(FRAG_MEAN, FRAG_SD))))
                start = rng.randint(0, len(tx) - flen)
                frag = tx[start : start + flen]
                # dUTP / reverse-stranded: R1 is antisense to the transcript, R2 sense
                read1 = _mutate(rng, revcomp(frag)[:READ_LEN])
                read2 = _mutate(rng, frag[:READ_LEN])
                n += 1
                r1.write(f"@{name}.{n}/1\n{read1}\n+\n{qual}\n")
                r2.write(f"@{name}.{n}/2\n{read2}\n+\n{qual}\n")
    return str(r1_path), str(r2_path)


def write_gtf(path: Path, genes: list[dict]) -> None:
    with open(path, "w") as fh:
        for g in genes:
            gid, strand = g["gene_id"], g["strand"]
            (a1, _), (_, b2) = g["exons"]
            attrs = f'gene_id "{gid}"; transcript_id "{gid}.1"; gene_name "{gid}";'
            fh.write(f"chr1\te2e\tgene\t{a1}\t{b2}\t.\t{strand}\t.\t{attrs}\n")
            fh.write(f"chr1\te2e\ttranscript\t{a1}\t{b2}\t.\t{strand}\t.\t{attrs}\n")
            for n, (a, b) in enumerate(g["exons"], 1):
                fh.write(f'chr1\te2e\texon\t{a}\t{b}\t.\t{strand}\t.\t{attrs} exon_number "{n}";\n')


def main(argv: list[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="e2e_data")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    out = Path(args.out)
    (out / "reference").mkdir(parents=True, exist_ok=True)
    (out / "fastq").mkdir(parents=True, exist_ok=True)

    ref_genome, genes = build_genome(rng)
    with open(out / "reference" / "genome.fa", "w") as fh:
        fh.write(">chr1\n")
        for i in range(0, len(ref_genome), 60):
            fh.write(ref_genome[i : i + 60] + "\n")
    write_gtf(out / "reference" / "genes.gtf", genes)

    sample_genome, snps = plant_snps(rng, ref_genome, genes)
    tx_seqs = {g["gene_id"]: transcript_seq(sample_genome, g) for g in genes}

    shuffled = rng.sample(genes, len(genes))
    up = sorted(g["gene_id"] for g in shuffled[:N_UP])
    down = sorted(g["gene_id"] for g in shuffled[N_UP : N_UP + N_DOWN])

    rows = []
    for name, condition in SAMPLES:
        counts = {}
        for g in genes:
            mean = g["base_mean"]
            if condition == "treated" and g["gene_id"] in up:
                mean *= FOLD
            elif condition == "treated" and g["gene_id"] in down:
                mean /= FOLD
            counts[g["gene_id"]] = _poisson(rng, mean)
        r1, r2 = simulate_sample(rng, tx_seqs, counts, out / "fastq", name)
        rows.append((name, condition, r1, r2))

    with open(out / "samples.tsv", "w") as fh:
        fh.write("name\tcondition\tfastq_r1\tfastq_r2\n")
        for row in rows:
            fh.write("\t".join(row) + "\n")

    truth = {
        "genome_length": len(ref_genome),
        "read_length": READ_LEN,
        "stranded": "reverse",
        "contrast": {"numerator": "treated", "denominator": "control"},
        "de_up": up,
        "de_down": down,
        "fold_change": FOLD,
        "snps": snps,
        "genes": [g["gene_id"] for g in genes],
    }
    (out / "truth.json").write_text(json.dumps(truth, indent=2) + "\n")
    print(f"wrote {out}/ (genome {len(ref_genome)} bp, {len(genes)} genes, {len(rows)} samples)")
    return out


if __name__ == "__main__":
    main()
