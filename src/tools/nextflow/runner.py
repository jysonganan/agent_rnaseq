"""NextflowRunner: submit, poll, and cancel Nextflow pipeline runs."""

from __future__ import annotations

import enum
import subprocess
import uuid
from dataclasses import dataclass, field


class NextflowStatus(enum.StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"
    unknown = "unknown"


@dataclass
class NextflowRunConfig:
    """Configuration for a Nextflow pipeline run."""

    workflow_path: str
    profile: str = "local"
    params: dict = field(default_factory=dict)
    work_dir: str | None = None
    extra_args: list[str] = field(default_factory=list)


class NextflowRunner:
    """Submits and tracks Nextflow pipeline runs as background subprocesses."""

    def __init__(self, nextflow_bin: str = "nextflow") -> None:
        self._bin = nextflow_bin
        self._procs: dict[str, subprocess.Popen] = {}  # type: ignore[type-arg]

    def _build_cmd(self, config: NextflowRunConfig) -> list[str]:
        cmd = [self._bin, "run", config.workflow_path, "-profile", config.profile]
        if config.work_dir:
            cmd += ["-work-dir", config.work_dir]
        for key, value in config.params.items():
            cmd += [f"--{key}", str(value)]
        cmd.extend(config.extra_args)
        return cmd

    def submit(self, config: NextflowRunConfig) -> str:
        """Launch Nextflow in the background and return an opaque run ID."""
        run_id = str(uuid.uuid4())
        cmd = self._build_cmd(config)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._procs[run_id] = proc
        return run_id

    def poll(self, run_id: str) -> NextflowStatus:
        """Return current status for a previously submitted run."""
        proc = self._procs.get(run_id)
        if proc is None:
            return NextflowStatus.unknown
        ret = proc.poll()
        if ret is None:
            return NextflowStatus.running
        return NextflowStatus.completed if ret == 0 else NextflowStatus.failed

    def cancel(self, run_id: str) -> None:
        """Terminate the Nextflow process for the given run ID."""
        proc = self._procs.get(run_id)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
