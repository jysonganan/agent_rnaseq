"""Opt-in end-to-end executor test (real Nextflow / tools / AWS). Skipped unless E2E_EXECUTOR is set.

Environment:
  E2E_EXECUTOR      local | nextflow | aws_batch                      (required to run)
  E2E_STUB          1 → Nextflow -stub-run (wiring only; needs just Java + Nextflow)
  E2E_DATA_DIR      existing dataset (make_test_data.py + prepare_reference.sh);
                    default: generated into the test's tmp dir
  E2E_TOOLS_IMAGE   build the reference with `prepare_reference.sh --docker <image>`
  E2E_OUTPUT_ROOT   where outputs/DB/report go (default: tmp dir)
  E2E_STAGES        comma-separated stage list (default depends on stub/real)
  E2E_S3_PREFIX     aws_batch only: s3://<S3_ARTIFACT_BUCKET>/e2e/<id> for uploaded inputs
  NEXTFLOW_LOCAL_PROFILE, NEXTFLOW_TOOLS_IMAGE, S3_ARTIFACT_BUCKET, AWS_BATCH_JOB_QUEUE, ...
                    passed through to the app settings

See docs/testing/executor_e2e.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.harness import E2EConfig, execute, open_db, register_run, verify, write_report

REPO = Path(__file__).resolve().parents[2]
EXECUTOR = os.environ.get("E2E_EXECUTOR")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not EXECUTOR, reason="set E2E_EXECUTOR to run the end-to-end test"),
]


def _prepare_data(tmp_path: Path, stub: bool) -> Path:
    if os.environ.get("E2E_DATA_DIR"):
        return Path(os.environ["E2E_DATA_DIR"]).resolve()
    data = tmp_path / "e2e_data"
    subprocess.run(
        [sys.executable, str(REPO / "scripts/e2e/make_test_data.py"), "--out", str(data)],
        check=True,
    )
    prep = [str(REPO / "scripts/e2e/prepare_reference.sh"), str(data)]
    if stub:
        prep.append("--stub")
    elif os.environ.get("E2E_TOOLS_IMAGE"):
        prep += ["--docker", os.environ["E2E_TOOLS_IMAGE"]]
    subprocess.run(prep, check=True)
    return data


def test_executor_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import get_settings

    stub = os.environ.get("E2E_STUB") == "1"
    if stub:
        monkeypatch.setenv("NEXTFLOW_EXTRA_ARGS", "-stub-run")
        monkeypatch.setenv(
            "NEXTFLOW_LOCAL_PROFILE", os.environ.get("NEXTFLOW_LOCAL_PROFILE", "localtools,test")
        )
    get_settings.cache_clear()

    data_dir = _prepare_data(tmp_path, stub)
    out = Path(os.environ.get("E2E_OUTPUT_ROOT") or tmp_path / "out").resolve()
    out.mkdir(parents=True, exist_ok=True)
    stages = [s for s in os.environ.get("E2E_STAGES", "").split(",") if s]
    cfg = E2EConfig(
        executor=EXECUTOR or "",
        data_dir=data_dir,
        output_root=out,
        stub=stub,
        stages=stages,
        s3_prefix=os.environ.get("E2E_S3_PREFIX"),
    )
    truth = json.loads((data_dir / "truth.json").read_text())

    db = open_db(out / "e2e.sqlite")
    run_id = register_run(db, cfg, truth)
    status = execute(db, cfg, run_id)
    checks = verify(db, run_id, cfg, truth)
    report = write_report(cfg, run_id, checks)

    lines = [f"{'PASS' if c.ok else 'FAIL'}  {c.name}  {c.detail}" for c in checks]
    print(f"\nrun {run_id} → {status}; report: {report}\n" + "\n".join(lines))
    failed = [c for c in checks if not c.ok]
    assert not failed, "\n".join(f"{c.name}: {c.detail}" for c in failed)
