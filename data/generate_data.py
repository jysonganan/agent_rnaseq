"""Generate synthetic paired-end FASTQ files for the agent_rnaseq demo.

Produces 8 .fastq.gz files (4 samples × 2 reads) in the data/ directory.
Each sample has 2 000 read pairs, 100 bp, random sequences with Illumina-style
quality scores.  No real genome alignment is required — these are demo files
used with dry_run=True mode.

Usage:
    python data/generate_data.py          # from project root
    python generate_data.py               # from data/ directory
"""

from __future__ import annotations

import gzip
import random
from pathlib import Path

SAMPLES = [
    ("ctrl_1",  "control",   1, 42),
    ("ctrl_2",  "control",   2, 43),
    ("treat_1", "treatment", 1, 44),
    ("treat_2", "treatment", 2, 45),
]

N_READS  = 2_000
READ_LEN = 100
BASES    = "ACGT"

# Treatment samples get slightly elevated GC to simulate real composition shift
GC_BIAS: dict[str, float] = {
    "control":   0.50,
    "treatment": 0.55,
}


def _seq(rng: random.Random, length: int, gc: float) -> str:
    at = 1.0 - gc
    weights = [at / 2, gc / 2, gc / 2, at / 2]   # A C G T
    return "".join(rng.choices(BASES, weights=weights, k=length))


def _qual(rng: random.Random, length: int) -> str:
    """Phred+33 quality string, scores 20–40 (typical Illumina)."""
    return "".join(chr(rng.randint(53, 73)) for _ in range(length))


def _write_fastq(path: Path, rng: random.Random, gc: float) -> None:
    with gzip.open(path, "wt") as fh:
        for i in range(1, N_READS + 1):
            seq  = _seq(rng, READ_LEN, gc)
            qual = _qual(rng, READ_LEN)
            fh.write(f"@read_{i:05d}\n{seq}\n+\n{qual}\n")


def generate(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, condition, _rep, seed in SAMPLES:
        rng = random.Random(seed)
        gc  = GC_BIAS[condition]
        for mate in (1, 2):
            path = out_dir / f"{name}_R{mate}.fastq.gz"
            _write_fastq(path, rng, gc)
            kb = path.stat().st_size / 1024
            print(f"  wrote {path.name:30s}  {kb:5.1f} KB")
    print(f"\n{4 * 2} files written to {out_dir.resolve()}")


if __name__ == "__main__":
    here = Path(__file__).parent
    generate(here)
