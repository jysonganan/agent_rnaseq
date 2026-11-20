"""End-to-end harness: register the synthetic dataset, execute a run, verify the results.

Used by ``tests/e2e/test_executor_e2e.py`` (opt-in via ``E2E_EXECUTOR``) and by unit tests
that drive it with a fake ``nextflow``. See ``docs/testing/executor_e2e.md``.
"""

from __future__ import annotations

import gzip
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

HEAVY_STAGES = ("qc", "alignment", "quantification", "variant_calling")
STUB_STAGES = ["qc", "alignment", "quantification", "variant_calling"]
REAL_STAGES = [
    "qc",
    "alignment",
    "quantification",
    "variant_calling",
    "differential_expression",
    "visualization",
    "report",
]


@dataclass
class E2EConfig:
    executor: str  # local | nextflow | aws_batch
    data_dir: Path
    output_root: Path
    stub: bool = False
    stages: list[str] = field(default_factory=list)
    s3_prefix: str | None = None  # aws_batch: where inputs are uploaded (s3://bucket/e2e/<id>)
    cpus: int = 2
    memory_gb: int = 4

    def __post_init__(self) -> None:
        if not self.stages:
            self.stages = list(STUB_STAGES if self.stub else REAL_STAGES)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


# ── setup ──────────────────────────────────────────────────────────────────────


def open_db(path: Path) -> Session:
    import src.db.models  # noqa: F401  (register models)
    from src.db.base import Base

    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _samples(data_dir: Path) -> list[dict[str, str]]:
    rows = (data_dir / "samples.tsv").read_text().splitlines()[1:]
    out = []
    for row in rows:
        name, condition, _, _ = row.split("\t")
        out.append(
            {
                "name": name,
                "condition": condition,
                "r1": str(data_dir / "fastq" / f"{name}_R1.fq.gz"),
                "r2": str(data_dir / "fastq" / f"{name}_R2.fq.gz"),
            }
        )
    return out


def upload_inputs(data_dir: Path, s3_prefix: str) -> dict[str, str]:
    """Upload FASTQs + reference (incl. STAR index) to S3; return local→s3 path map."""
    from src.aws.config import get_aws_config
    from src.aws.s3 import S3FileManager

    cfg = get_aws_config()
    s3 = S3FileManager(cfg.bucket, region=cfg.region, endpoint_url=cfg.endpoint_url)
    mapping: dict[str, str] = {}
    for sub in ("fastq", "reference"):
        for path in sorted((data_dir / sub).rglob("*")):
            if path.is_file():
                uri = f"{s3_prefix.rstrip('/')}/{path.relative_to(data_dir).as_posix()}"
                s3.upload(str(path), uri)
                mapping[str(path)] = uri
    mapping[str(data_dir / "reference" / "star")] = f"{s3_prefix.rstrip('/')}/reference/star"
    return mapping


def register_run(db: Session, cfg: E2EConfig, truth: dict[str, Any]) -> str:
    from src.db.enums import Aligner, AlignmentMode, PipelineType, RunStatus, SampleType
    from src.db.models.auth import APIKey
    from src.db.models.genome import ReferenceGenome
    from src.db.models.project import Project, RunSample, Sample
    from src.db.models.run import AnalysisRun

    ref = cfg.data_dir / "reference"
    paths = {
        "fasta": str(ref / "genome.fa"),
        "gtf": str(ref / "genes.gtf"),
        "star": str(ref / "star"),
    }
    samples = _samples(cfg.data_dir)
    if cfg.executor == "aws_batch":
        assert cfg.s3_prefix, "aws_batch needs E2E_S3_PREFIX"
        mapping = upload_inputs(cfg.data_dir, cfg.s3_prefix)
        paths = {k: mapping[v] for k, v in paths.items()}
        for s in samples:
            s["r1"], s["r2"] = mapping[s["r1"]], mapping[s["r2"]]

    key = APIKey(key_hash=uuid.uuid4().hex, name="e2e", created_by="e2e")
    project = Project(name="e2e", owner="e2e")
    genome = ReferenceGenome(
        name=f"e2e-{uuid.uuid4().hex[:8]}",
        species="Synthetic",
        build="e2e1",
        fasta_path=paths["fasta"],
        gtf_path=paths["gtf"],
        star_index_path=paths["star"],
    )
    db.add_all([key, project, genome])
    db.flush()
    rows = [
        Sample(
            project_id=project.id,
            name=s["name"],
            sample_type=SampleType.bulk_rnaseq,
            condition=s["condition"],
            fastq_r1_path=s["r1"],
            fastq_r2_path=s["r2"],
            is_paired_end=True,
        )
        for s in samples
    ]
    db.add_all(rows)
    db.flush()
    run = AnalysisRun(
        project_id=project.id,
        genome_id=genome.id,
        created_by=key.id,
        name=f"e2e-{cfg.executor}{'-stub' if cfg.stub else ''}",
        status=RunStatus.pending,
        pipeline_type=PipelineType.bulk_rnaseq,
        alignment_mode=AlignmentMode.genome,
        aligner=Aligner.star,
        run_config={
            "stages": cfg.stages,
            "de_contrasts": [truth["contrast"]],
            "read_length": truth["read_length"],
            "execution": {
                "executor": cfg.executor,
                "cpus": cfg.cpus,
                "memory_gb": cfg.memory_gb,
            },
        },
    )
    db.add(run)
    db.flush()
    for r in rows:
        db.add(RunSample(run_id=run.id, sample_id=r.id))
    db.commit()
    return str(run.id)


def execute(db: Session, cfg: E2EConfig, run_id: str) -> str:
    from src.agents.run_events import NullRunEvents
    from src.api.background.runner import execute_run_sync

    status = execute_run_sync(db, run_id, events=NullRunEvents(), output_root=str(cfg.output_root))
    return str(status)


# ── verification ───────────────────────────────────────────────────────────────


def _read_text(path: str, localize: Any) -> str:
    local = localize(path)
    opener = gzip.open if local.endswith(".gz") else open
    with opener(local, "rt") as fh:
        return fh.read()


def _localizer(cfg: E2EConfig) -> Any:
    if cfg.executor != "aws_batch":
        return lambda p: p
    from src.tools.nextflow.storage import storage_for

    return storage_for("s3://x", str(cfg.output_root / "verify_cache")).localize


def _exists(path: str) -> bool:
    if path.startswith("s3://"):
        from src.aws.config import get_aws_config
        from src.aws.s3 import S3FileManager

        cfg = get_aws_config()
        return S3FileManager(cfg.bucket, region=cfg.region, endpoint_url=cfg.endpoint_url).exists(
            path
        )
    return os.path.exists(path)


def verify(db: Session, run_id: str, cfg: E2EConfig, truth: dict[str, Any]) -> list[Check]:
    from src.db.enums import StageName, StageStatus
    from src.db.models.results import DEGResult
    from src.db.models.run import AnalysisRun, Artifact, PipelineStage

    checks: list[Check] = []
    run = db.get(AnalysisRun, uuid.UUID(run_id))
    state = run.agent_state or {}
    n_samples = len(run.sample_associations)
    checks.append(Check("run completed", str(run.status) == "completed", run.error_message or ""))

    for stage in cfg.stages:
        rows = db.query(PipelineStage).filter_by(stage_name=StageName(stage)).all()
        expected = n_samples if stage in HEAVY_STAGES else 1
        done = [r for r in rows if r.status == StageStatus.completed]
        checks.append(
            Check(f"{stage}: {expected} completed row(s)", len(done) == expected, f"{len(done)}")
        )
        want_exec = cfg.executor if stage in HEAVY_STAGES else "local"
        execs = {str(r.executor) for r in done}
        checks.append(Check(f"{stage}: executor={want_exec}", execs == {want_exec}, str(execs)))
        versions = {r.tool_version for r in done}
        has_versions = bool(done) and None not in versions
        checks.append(Check(f"{stage}: tool_version recorded", has_versions, str(versions)))
        if cfg.stub and stage in HEAVY_STAGES:
            stub_ok = all(v and "stub" in v for v in versions)
            checks.append(Check(f"{stage}: ran Nextflow stubs", stub_ok, str(versions)))

    for art in db.query(Artifact).filter_by(run_id=run.id).all():
        checks.append(Check(f"artifact exists: {Path(art.path).name}", _exists(art.path)))

    if cfg.stub:
        return checks

    outs = state.get("stage_outputs") or {}
    localize = _localizer(cfg)

    if "alignment" in cfg.stages:
        rates = [
            (s.get("output") or {}).get("alignment_stats", {}).get("uniquely_mapped_pct", 0.0)
            for s in (outs.get("alignment") or {}).get("samples", {}).values()
        ]
        checks.append(
            Check("alignment: uniquely mapped >= 70%", bool(rates) and min(rates) >= 70, str(rates))
        )

    if "quantification" in cfg.stages:
        fracs = []
        for s in (outs.get("quantification") or {}).get("samples", {}).values():
            o = s.get("output") or {}
            fracs.append(round(o.get("counted_reads", 0) / max(1, o.get("total_reads", 1)), 3))
        checks.append(
            Check(
                "quantification: >= 70% reads counted (reverse-stranded)",
                bool(fracs) and min(fracs) >= 0.7,
                str(fracs),
            )
        )

    if "differential_expression" in cfg.stages:
        rows = {r.gene_id: r for r in db.query(DEGResult).filter_by(run_id=run.id).all()}

        def sig(g: str, sign: int) -> bool:
            r = rows.get(g)
            return bool(
                r and r.padj is not None and r.padj < 0.05 and sign * (r.log2_fold_change or 0) > 1
            )

        up = [g for g in truth["de_up"] if sig(g, 1)]
        down = [g for g in truth["de_down"] if sig(g, -1)]
        truth_de = set(truth["de_up"]) | set(truth["de_down"])
        false_pos = [
            g
            for g, r in rows.items()
            if g not in truth_de
            and r.padj is not None
            and r.padj < 0.05
            and abs(r.log2_fold_change or 0) > 1
        ]
        checks.append(
            Check(
                "DESeq2 recovers >= 75% of true up genes",
                len(up) >= 0.75 * len(truth["de_up"]),
                f"{up}",
            )
        )
        checks.append(
            Check(
                "DESeq2 recovers >= 75% of true down genes",
                len(down) >= 0.75 * len(truth["de_down"]),
                f"{down}",
            )
        )
        checks.append(Check("DESeq2 false positives <= 2", len(false_pos) <= 2, f"{false_pos}"))

    if "variant_calling" in cfg.stages:
        found = 0
        for s in (outs.get("variant_calling") or {}).get("samples", {}).values():
            vcf = (s.get("output") or {}).get("filtered_vcf_path")
            if not vcf:
                continue
            calls = {
                (f[0], int(f[1]), f[3], f[4])
                for f in (
                    ln.split("\t")
                    for ln in _read_text(vcf, localize).splitlines()
                    if ln and not ln.startswith("#")
                )
                if f[6] in ("PASS", ".")
            }
            found = max(
                found,
                sum((v["chrom"], v["pos"], v["ref"], v["alt"]) in calls for v in truth["snps"]),
            )
        checks.append(
            Check("GATK calls >= 2 of 3 planted SNPs (best sample)", found >= 2, f"{found}/3")
        )

    if "report" in cfg.stages:
        html = ((outs.get("report") or {}).get("output") or {}).get("html_report_path", "")
        checks.append(Check("report.html written", bool(html) and _exists(html), html))

    return checks


def write_report(cfg: E2EConfig, run_id: str, checks: list[Check]) -> Path:
    path = cfg.output_root / "e2e_report.json"
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "executor": cfg.executor,
                "stub": cfg.stub,
                "stages": cfg.stages,
                "passed": all(c.ok for c in checks),
                "checks": [asdict(c) for c in checks],
            },
            indent=2,
        )
    )
    return path
