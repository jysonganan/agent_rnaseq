"""Default ``MockToolRegistry`` for dry runs (``dry_run=true``).

Each fixture in ``src/tools/mock_outputs/`` is validated against its ``ToolOutput`` model on
load (safety_policy Rule 2), then wrapped as the stage's ``StageOutput`` dict so dry-run
``RunState.stage_outputs`` has the same shape as a real run.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from src.agents.base_agent import MockToolRegistry
from src.tools.alignment.star import STARAlignOutput
from src.tools.de.deseq2 import DESeq2Output
from src.tools.gsea.reactome import ReactomeGSEAOutput
from src.tools.qc.fastqc import FastQCOutput
from src.tools.qc.rseqc import RSeQCOutput
from src.tools.quantification.htseq import HTSeqOutput
from src.tools.report.compile import ReportOutput
from src.tools.scrna.scanpy_tool import ScanpyOutput
from src.tools.splicing.rmats import RMATSOutput
from src.tools.variant.gatk import GATKVariantFilterOutput
from src.tools.viz.streamlit_prep import StreamlitDataPrepOutput

FIXTURE_DIR = Path(__file__).parent / "mock_outputs"

# stage → (fixture file, ToolOutput model)
STAGE_FIXTURES: dict[str, tuple[str, type[BaseModel]]] = {
    "qc": ("fastqc_output.json", FastQCOutput),
    "alignment": ("star_align_output.json", STARAlignOutput),
    "alignment_qc": ("rseqc_output.json", RSeQCOutput),
    "quantification": ("htseq_output.json", HTSeqOutput),
    "variant_calling": ("gatk_variant_filter_output.json", GATKVariantFilterOutput),
    "splicing": ("rmats_output.json", RMATSOutput),
    "differential_expression": ("deseq2_output.json", DESeq2Output),
    "gsea": ("reactome_gsea_output.json", ReactomeGSEAOutput),
    "scrna_seq": ("scanpy_output.json", ScanpyOutput),
    "visualization": ("streamlit_prep_output.json", StreamlitDataPrepOutput),
    "report": ("report_output.json", ReportOutput),
}


def load_fixture(stage: str) -> BaseModel:
    filename, model = STAGE_FIXTURES[stage]
    with open(FIXTURE_DIR / filename) as fh:
        return model.model_validate(json.load(fh))


@lru_cache(maxsize=1)
def _stage_outputs() -> dict[str, dict]:
    outputs = {}
    for stage in STAGE_FIXTURES:
        tool_out = load_fixture(stage)
        dumped = tool_out.model_dump()
        outputs[stage] = {
            "stage_name": stage,
            "status": "completed",
            "output": dumped,
            "tool_version": dumped.get("tool_version"),
            "summary": None,
            "mock": True,
        }
    return outputs


def load_default_registry() -> MockToolRegistry:
    """Registry keyed by stage name, as ``BaseStageAgent.execute`` looks it up."""
    registry = MockToolRegistry()
    for stage, output in _stage_outputs().items():
        registry.register(stage, json.loads(json.dumps(output)))
    return registry
