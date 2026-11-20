"""Static checks for the e2e/AWS assets: pinned tool env and the Batch CloudFormation stack."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

# tool_versions.txt name → conda package name
CONDA_NAMES = {
    "FastQC": "fastqc",
    "STAR": "star",
    "samtools": "samtools",
    "GATK": "gatk4",
    "Salmon": "salmon",
    "HTSeq": "htseq",
    "RSEM": "rsem",
    "Nextflow": "nextflow",
    "R": "r-base",
    "DESeq2": "bioconductor-deseq2",
    "fgsea": "bioconductor-fgsea",
    "reactome.db": "bioconductor-reactome.db",
    "deepTools": "deeptools",
}
NOT_IN_CONDA_ENV = {"RSeQC", "rMATS", "Scanpy", "AWSCLI", "CellRanger"}


def _pins() -> dict[str, str]:
    pins = {}
    for line in (REPO / "docker/tool_versions.txt").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, version = line.split("=", 1)
            pins[name.strip()] = version.strip()
    return pins


def test_conda_env_matches_tool_versions() -> None:
    env = yaml.safe_load((REPO / "environment/rnaseq-tools.yml").read_text())
    deps = {
        d.split("=")[0]: d.split("=", 1)[1]
        for d in env["dependencies"]
        if isinstance(d, str) and "=" in d
    }
    for tool, version in _pins().items():
        if tool in NOT_IN_CONDA_ENV:
            continue
        assert tool in CONDA_NAMES, f"map {tool} to a conda package in this test"
        assert deps.get(CONDA_NAMES[tool]) == version, (tool, deps.get(CONDA_NAMES[tool]))


def test_tools_image_contains_nextflow_task_requirements() -> None:
    dockerfile = (REPO / "docker/Dockerfile.tools").read_text()
    assert "procps" in dockerfile  # `ps` for Nextflow task metrics
    assert "awscli-exe-linux-x86_64-${AWSCLI_VERSION}" in dockerfile  # Batch S3 staging
    assert f"AWSCLI_VERSION={_pins()['AWSCLI']}" in dockerfile
    api = (REPO / "docker/Dockerfile.api").read_text()
    assert f"NEXTFLOW_VERSION={_pins()['Nextflow']}" in api


class _CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):  # type: ignore[no-untyped-def]
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {suffix: value}


_CfnLoader.add_multi_constructor("!", _tag)


def _stack() -> dict:
    return yaml.load((REPO / "infra/aws-batch/batch-stack.yaml").read_text(), Loader=_CfnLoader)


def test_bucket_is_encrypted_private_tls_only_and_expiring() -> None:
    res = _stack()["Resources"]
    bucket = res["ArtifactBucket"]["Properties"]
    assert (
        bucket["BucketEncryption"]["ServerSideEncryptionConfiguration"][0][
            "ServerSideEncryptionByDefault"
        ]["SSEAlgorithm"]
        == "AES256"
    )
    assert all(bucket["PublicAccessBlockConfiguration"].values())
    prefixes = {r.get("Prefix") for r in bucket["LifecycleConfiguration"]["Rules"]}
    assert {"nextflow-work/", "e2e/", "runs/"} <= prefixes
    deny = res["ArtifactBucketTlsOnly"]["Properties"]["PolicyDocument"]["Statement"][0]
    assert deny["Effect"] == "Deny" and deny["Condition"]["Bool"]["aws:SecureTransport"] == "false"


def test_compute_scales_to_zero_and_images_are_immutable() -> None:
    res = _stack()["Resources"]
    compute = res["ComputeEnvironment"]["Properties"]["ComputeResources"]
    assert compute["MinvCpus"] == 0 and compute["DesiredvCpus"] == 0
    assert res["ToolsRepository"]["Properties"]["ImageTagMutability"] == "IMMUTABLE"


def test_s3_permissions_scoped_to_the_bucket() -> None:
    res = _stack()["Resources"]
    statements = res["WorkerPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    statements += res["InstanceRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    for st in statements:
        if any(a.startswith("s3:") for a in st["Action"]):
            assert st["Resource"] != "*", st


def test_outputs_feed_the_app_settings() -> None:
    assert set(_stack()["Outputs"]) == {
        "BucketName",
        "JobQueueArn",
        "ToolsRepositoryUri",
        "WorkerPolicyArn",
    }


def test_shell_scripts_parse() -> None:
    scripts = [*REPO.glob("infra/aws-batch/*.sh"), REPO / "scripts/e2e/prepare_reference.sh"]
    for script in scripts:
        subprocess.run(["bash", "-n", str(script)], check=True)
