"""Always-on tests for the e2e tooling (no Nextflow / tools / AWS needed).

* the synthetic dataset really encodes its truth (strandedness, fold changes, SNPs);
* the harness runs the full app path against a fake ``nextflow`` that publishes exactly what
  the ``stub:`` blocks in ``nextflow/modules/*.nf`` publish, and its verification passes.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.e2e.harness import E2EConfig, execute, open_db, register_run, verify

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "e2e"))
import make_test_data  # noqa: E402


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("e2e") / "data"
    make_test_data.main(["--out", str(out)])
    subprocess.run([str(REPO / "scripts/e2e/prepare_reference.sh"), str(out), "--stub"], check=True)
    return out


# ── dataset truth ──────────────────────────────────────────────────────────────


def _assign_reads(data: Path, sample: str) -> tuple[Counter, int]:
    """Assign read pairs to genes by exact 25-mer lookup of R2 in transcript sequences."""
    genome = "".join((data / "reference/genome.fa").read_text().split("\n")[1:])
    genes = []
    for line in (data / "reference/genes.gtf").read_text().splitlines():
        f = line.split("\t")
        if f[2] == "exon":
            gid = f[8].split('"')[1]
            if not genes or genes[-1][0] != gid:
                genes.append((gid, f[6], []))
            genes[-1][2].append((int(f[3]), int(f[4])))
    kmers: dict[str, tuple[str, str]] = {}
    for gid, strand, exons in genes:
        tx = "".join(genome[a - 1 : b] for a, b in exons)
        sense = tx if strand == "+" else make_test_data.revcomp(tx)
        for i in range(0, len(sense) - 25, 5):
            kmers[sense[i : i + 25]] = (gid, "sense")
            kmers[make_test_data.revcomp(sense[i : i + 25])] = (gid, "anti")
    counts: Counter = Counter()
    antisense_r2 = 0
    with gzip.open(data / "fastq" / f"{sample}_R2.fq.gz", "rt") as fh:
        for i, line in enumerate(fh):
            if i % 4 != 1:
                continue
            for off in range(0, 50, 5):
                hit = kmers.get(line[off : off + 25])
                if hit:
                    counts[hit[0]] += 1
                    antisense_r2 += hit[1] == "anti"
                    break
    return counts, antisense_r2


def test_dataset_is_reverse_stranded_and_encodes_fold_changes(dataset: Path) -> None:
    truth = json.loads((dataset / "truth.json").read_text())
    ctrl, anti_c = _assign_reads(dataset, "ctrl_1")
    trt, anti_t = _assign_reads(dataset, "treat_1")
    assert anti_c == anti_t == 0  # R2 is always sense → htseq --stranded reverse
    for g in truth["de_up"]:
        assert trt[g] / max(1, ctrl[g]) > 2.0, g
    for g in truth["de_down"]:
        assert trt[g] / max(1, ctrl[g]) < 0.5, g


def test_snps_are_in_reads_not_reference(dataset: Path) -> None:
    truth = json.loads((dataset / "truth.json").read_text())
    genome = "".join((dataset / "reference/genome.fa").read_text().split("\n")[1:])
    for snp in truth["snps"]:
        assert genome[snp["pos"] - 1] == snp["ref"]
    assert len({s["gene"] for s in truth["snps"]}) == 3


def test_dataset_is_deterministic(tmp_path: Path) -> None:
    a = make_test_data.main(["--out", str(tmp_path / "a")])
    b = make_test_data.main(["--out", str(tmp_path / "b")])
    assert (a / "truth.json").read_text() == (b / "truth.json").read_text()
    assert (a / "reference/genome.fa").read_bytes() == (b / "reference/genome.fa").read_bytes()


# ── harness against a stub-equivalent fake nextflow ───────────────────────────


def _arg(cmd: list[str], name: str) -> str | None:
    return cmd[cmd.index(name) + 1] if name in cmd else None


class StubNextflow:
    """Publishes what the `stub:` blocks in nextflow/modules/*.nf publish."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, cmd, stdout=None, stderr=None, cwd=None):  # type: ignore[no-untyped-def]
        self.commands.append(cmd)
        wf, sid, out = _arg(cmd, "--workflow"), _arg(cmd, "--sample_id"), _arg(cmd, "--output_dir")
        os.makedirs(out, exist_ok=True)

        def w(name: str, data: bytes | str) -> None:
            Path(out, name).write_bytes(data.encode() if isinstance(data, str) else data)

        if wf == "qc":
            for fq in filter(None, (_arg(cmd, "--fastq_r1"), _arg(cmd, "--fastq_r2"))):
                stem = Path(fq).name.replace(".fq.gz", "")
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    z.writestr(f"{stem}_fastqc/summary.txt", "PASS\tBasic Statistics\tx\n")
                w(f"{stem}_fastqc.zip", buf.getvalue())
                w(f"{stem}_fastqc.html", "<html>stub</html>")
            w(f"{sid}.fastqc.version.txt", "FastQC stub\n")
        elif wf == "alignment":
            w(f"{sid}_Log.final.out", "  Uniquely mapped reads % |\t90.00%\n")
            w(f"{sid}_SJ.out.tab", "")
            w(f"{sid}.sorted.bam", "")
            w(f"{sid}.sorted.bam.bai", "")
            w(f"{sid}.star.version.txt", "STAR stub\n")
            w(f"{sid}.samtools.version.txt", "samtools stub\n")
        elif wf == "quantification":
            w(f"{sid}_counts.tsv", "GENE_A\t10\nGENE_B\t20\n__no_feature\t3\n")
            w(f"{sid}.htseq.version.txt", "HTSeq stub\n")
        elif wf == "alignment_qc":  # mirrors nextflow/modules/rseqc.nf stub
            assert _arg(cmd, "--bed") and Path(_arg(cmd, "--bed")).is_file()
            w(
                f"{sid}.rseqc_read_distribution.txt",
                "Total Reads                   1000\nTotal Tags                    1000\n"
                "Total Assigned Tags           900\n"
                "Group               Total_bases         Tag_count           Tags/Kb\n"
                "CDS_Exons           1000                800                 800.00\n",
            )
            w(
                f"{sid}.rseqc_infer_experiment.txt",
                "This is PairEnd Data\nFraction of reads failed to determine: 0.0100\n"
                'Fraction of reads explained by "1++,1--,2+-,2-+": 0.0100\n'
                'Fraction of reads explained by "1+-,1-+,2++,2--": 0.9800\n',
            )
            w(f"{sid}.rseqc.version.txt", "RSeQC stub\n")
        elif wf == "variant_calling":
            vcf = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\nchr1\t100\t.\tA\tG\t50\tPASS\n"
            w(f"{sid}.raw.vcf.gz", gzip.compress(vcf.encode()))
            w(f"{sid}.filtered.vcf.gz", gzip.compress(vcf.encode()))
            w(f"{sid}.gatk.version.txt", "GATK stub\n")
        proc = MagicMock()
        proc.poll.return_value = 0
        proc.returncode = 0
        return proc


def test_harness_stub_mode_passes_with_stub_equivalent_outputs(
    dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.config import get_settings

    monkeypatch.setenv("NEXTFLOW_EXTRA_ARGS", "-stub-run")
    monkeypatch.setenv("NEXTFLOW_LOCAL_PROFILE", "localtools,test")
    get_settings.cache_clear()

    cfg = E2EConfig(executor="nextflow", data_dir=dataset, output_root=tmp_path, stub=True)
    truth = json.loads((dataset / "truth.json").read_text())
    db = open_db(tmp_path / "e2e.sqlite")
    run_id = register_run(db, cfg, truth)
    fake = StubNextflow()
    with (
        patch("shutil.which", return_value="/usr/bin/nextflow"),
        patch("src.tools.nextflow.stage_runner.subprocess.Popen", fake),
        patch("src.tools.nextflow.stage_runner.time.sleep"),
    ):
        status = execute(db, cfg, run_id)
    checks = verify(db, run_id, cfg, truth)
    failed = [c for c in checks if not c.ok]
    assert status == "completed" and not failed, failed

    cmd = fake.commands[0]
    assert "-stub-run" in cmd
    assert _arg(cmd, "-profile") == "localtools,test"
    assert _arg(cmd, "--threads") == "2" and _arg(cmd, "--memory") == "4 GB"
    align = next(c for c in fake.commands if _arg(c, "--workflow") == "alignment")
    assert _arg(align, "--read_group") == "ctrl_1"


def test_verify_flags_missing_stage_rows(dataset: Path, tmp_path: Path) -> None:
    cfg = E2EConfig(executor="nextflow", data_dir=dataset, output_root=tmp_path, stub=True)
    truth = json.loads((dataset / "truth.json").read_text())
    db = open_db(tmp_path / "e2e.sqlite")
    run_id = register_run(db, cfg, truth)  # never executed
    checks = {c.name: c.ok for c in verify(db, run_id, cfg, truth)}
    assert checks["run completed"] is False
    assert checks["qc: 6 completed row(s)"] is False
