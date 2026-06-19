"""Integration test: QC → Alignment → Quantification → DE → GSEA.

All bioinformatics tool calls are mocked; the test verifies that each agent
correctly writes PipelineStage, DEGResult, and GSEAResult rows to the DB.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.specialists.alignment_agent import AlignmentAgent
from src.agents.specialists.de_agent import DEAgent
from src.agents.specialists.gsea_agent import GSEAAgent
from src.agents.specialists.qc_agent import QCAgent
from src.agents.specialists.quantification_agent import QuantificationAgent
from src.db.enums import StageStatus
from src.db.models.results import DEGResult, GSEAResult
from src.db.models.run import PipelineStage
from src.tools.alignment.samtools import SamtoolsOutput
from src.tools.alignment.star import STARAlignOutput
from src.tools.de.deseq2 import DESeq2Output
from src.tools.de.parsers import DEContrastSummary
from src.tools.gsea.reactome import ReactomeGSEAOutput
from src.tools.quantification.htseq import HTSeqOutput
from src.tools.qc.fastqc import FastQCOutput
from src.tools.qc.multiqc import MultiQCOutput

from tests.integration.conftest import FIXTURES_DIR, RUN_ID, SAMPLE_ID

_DE_CSV = (
    "gene_id,baseMean,log2FoldChange,lfcSE,stat,pvalue,padj\n"
    "ENSG001,1000.0,2.5,0.3,8.3,1e-16,5e-15\n"
    "ENSG002,500.0,-1.5,0.4,-3.75,0.0002,0.001\n"
    "ENSG003,200.0,0.3,0.5,0.6,0.5,0.8\n"
)

_GSEA_CSV = (
    "pathway_id,pathway_name,NES,pvalue,padj\n"
    "R-HSA-162582,Signal transduction,2.1,0.001,0.01\n"
    "R-HSA-1640170,Cell cycle,1.5,0.005,0.04\n"
)


def _mock_fastqc() -> FastQCOutput:
    return FastQCOutput(
        report_html_paths=["/out/qc/sample_fastqc.html"],
        report_zip_paths=["/out/qc/sample_fastqc.zip"],
        summary={"Basic Statistics": "PASS", "Per base sequence quality": "PASS"},
        tool_version="FastQC 0.11.9",
    )


def _mock_multiqc() -> MultiQCOutput:
    return MultiQCOutput(
        report_html_path="/out/qc/multiqc_report.html",
        data_dir="/out/qc/multiqc_data",
        parsed_metrics={},
        tool_version="MultiQC 1.14",
    )


def _mock_star() -> STARAlignOutput:
    return STARAlignOutput(
        bam_path="/out/align/sample.bam",
        bam_index_path="/out/align/sample.bam.bai",
        log_final_path="/out/align/Log.final.out",
        splice_junctions_path="/out/align/SJ.out.tab",
        gene_counts_path="/out/align/ReadsPerGene.out.tab",
        alignment_stats={"uniquely_mapped_pct": 90.0},
        tool_version="STAR 2.7.10a",
    )


def _mock_samtools() -> SamtoolsOutput:
    return SamtoolsOutput(
        sorted_bam_path="/out/align/sample_sorted.bam",
        bai_path="/out/align/sample_sorted.bam.bai",
        flagstat={"mapped": 9, "total": 10},
        tool_version="samtools 1.17",
    )


def _mock_htseq() -> HTSeqOutput:
    return HTSeqOutput(
        counts_path="/out/quant/counts.tsv",
        total_reads=1_000_000,
        counted_reads=950_000,
        no_feature_reads=30_000,
        ambiguous_reads=20_000,
        tool_version="HTSeq 2.0.2",
    )


def _mock_deseq2() -> DESeq2Output:
    return DESeq2Output(
        results_paths={"treatment_vs_control": "/out/de/treatment_vs_control.csv"},
        normalized_counts_path="/out/de/normalized_counts.csv",
        size_factors_path="/out/de/size_factors.csv",
        dispersion_plot_path="/out/de/dispersion_plot.pdf",
        pca_plot_path="/out/de/pca_plot.pdf",
        contrast_summaries={
            "treatment_vs_control": DEContrastSummary(
                total_genes=3, upregulated=1, downregulated=1, not_significant=1
            )
        },
        tool_version="DESeq2 1.42.0",
    )


def _mock_gsea() -> ReactomeGSEAOutput:
    return ReactomeGSEAOutput(
        results_path="/out/gsea/treatment_vs_control/gsea_results.csv",
        enrichment_plots_dir="/out/gsea/treatment_vs_control/plots",
        significant_pathway_count=2,
        tool_version="Reactome fgsea 1.26.0",
    )


def _qc_input() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "fastq_paths": [str(FIXTURES_DIR / "synthetic_R1.fastq.gz")],
        "output_dir": "/out/qc",
        "bam_path": None,
        "bam_index_path": None,
        "bed_annotation_path": None,
    }


def _align_input() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "fastq_r1": str(FIXTURES_DIR / "synthetic_R1.fastq.gz"),
        "fastq_r2": str(FIXTURES_DIR / "synthetic_R2.fastq.gz"),
        "genome_dir": "/ref/genome",
        "output_prefix": "/out/align/sample",
        "threads": 4,
    }


def _quant_input() -> dict:
    return {
        "run_id": RUN_ID,
        "sample_id": SAMPLE_ID,
        "quantification_method": "star_htseq",
        "output_dir": "/out/quant",
        "bam_path": "/out/align/sample_sorted.bam",
        "gtf_path": "/ref/hg38.gtf",
        "fastq_r1": None,
        "fastq_r2": None,
        "index_path": None,
        "rsem_reference": None,
    }


def _de_input() -> dict:
    return {
        "run_id": RUN_ID,
        "counts_matrix_path": "/out/quant/counts.tsv",
        "sample_metadata_path": "/out/metadata.csv",
        "contrasts": [{"name": "treatment_vs_control", "numerator": "treatment", "denominator": "control"}],
        "output_dir": "/out/de",
        "alpha": 0.05,
        "lfc_threshold": 0.0,
        "r_script_path": "/scripts/deseq2.R",
    }


def _gsea_input() -> dict:
    return {
        "run_id": RUN_ID,
        "de_results_paths": {"treatment_vs_control": "/out/de/treatment_vs_control.csv"},
        "output_dir": "/out/gsea",
        "organism": "human",
        "r_script_path": "/scripts/gsea.R",
    }


def test_all_five_stages_complete(db):
    with (
        patch("src.agents.specialists.qc_agent.run_fastqc", return_value=_mock_fastqc()),
        patch("src.agents.specialists.qc_agent.run_multiqc", return_value=_mock_multiqc()),
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_mock_htseq()),
        patch("src.agents.specialists.de_agent.run_deseq2", return_value=_mock_deseq2()),
        patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DE_CSV),
        patch("src.agents.specialists.gsea_agent.run_reactome_gsea", return_value=_mock_gsea()),
        patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV),
    ):
        QCAgent(db).run(_qc_input())
        AlignmentAgent(db).run(_align_input())
        QuantificationAgent(db).run(_quant_input())
        DEAgent(db).run(_de_input())
        GSEAAgent(db).run(_gsea_input())

    stages = db.query(PipelineStage).all()
    assert len(stages) == 5
    assert all(s.status == StageStatus.completed for s in stages)


def test_stage_names_match_pipeline_order(db):
    with (
        patch("src.agents.specialists.qc_agent.run_fastqc", return_value=_mock_fastqc()),
        patch("src.agents.specialists.qc_agent.run_multiqc", return_value=_mock_multiqc()),
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_mock_htseq()),
        patch("src.agents.specialists.de_agent.run_deseq2", return_value=_mock_deseq2()),
        patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DE_CSV),
        patch("src.agents.specialists.gsea_agent.run_reactome_gsea", return_value=_mock_gsea()),
        patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV),
    ):
        QCAgent(db).run(_qc_input())
        AlignmentAgent(db).run(_align_input())
        QuantificationAgent(db).run(_quant_input())
        DEAgent(db).run(_de_input())
        GSEAAgent(db).run(_gsea_input())

    stage_names = {str(s.stage_name) for s in db.query(PipelineStage).all()}
    assert stage_names == {"qc", "alignment", "quantification", "differential_expression", "gsea"}


def test_deg_results_written_to_db(db):
    with (
        patch("src.agents.specialists.qc_agent.run_fastqc", return_value=_mock_fastqc()),
        patch("src.agents.specialists.qc_agent.run_multiqc", return_value=_mock_multiqc()),
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_mock_htseq()),
        patch("src.agents.specialists.de_agent.run_deseq2", return_value=_mock_deseq2()),
        patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DE_CSV),
        patch("src.agents.specialists.gsea_agent.run_reactome_gsea", return_value=_mock_gsea()),
        patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV),
    ):
        QCAgent(db).run(_qc_input())
        AlignmentAgent(db).run(_align_input())
        QuantificationAgent(db).run(_quant_input())
        DEAgent(db).run(_de_input())
        GSEAAgent(db).run(_gsea_input())

    deg_rows = db.query(DEGResult).all()
    assert len(deg_rows) == 3
    gene_ids = {r.gene_id for r in deg_rows}
    assert "ENSG001" in gene_ids
    assert "ENSG002" in gene_ids
    assert "ENSG003" in gene_ids


def test_gsea_results_written_to_db(db):
    with (
        patch("src.agents.specialists.qc_agent.run_fastqc", return_value=_mock_fastqc()),
        patch("src.agents.specialists.qc_agent.run_multiqc", return_value=_mock_multiqc()),
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_mock_htseq()),
        patch("src.agents.specialists.de_agent.run_deseq2", return_value=_mock_deseq2()),
        patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DE_CSV),
        patch("src.agents.specialists.gsea_agent.run_reactome_gsea", return_value=_mock_gsea()),
        patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV),
    ):
        QCAgent(db).run(_qc_input())
        AlignmentAgent(db).run(_align_input())
        QuantificationAgent(db).run(_quant_input())
        DEAgent(db).run(_de_input())
        GSEAAgent(db).run(_gsea_input())

    gsea_rows = db.query(GSEAResult).all()
    assert len(gsea_rows) == 2
    pathway_ids = {r.pathway_id for r in gsea_rows}
    assert "R-HSA-162582" in pathway_ids
    assert "R-HSA-1640170" in pathway_ids


def test_deg_contrast_stored_correctly(db):
    with (
        patch("src.agents.specialists.qc_agent.run_fastqc", return_value=_mock_fastqc()),
        patch("src.agents.specialists.qc_agent.run_multiqc", return_value=_mock_multiqc()),
        patch("src.agents.specialists.alignment_agent.run_star_align", return_value=_mock_star()),
        patch("src.agents.specialists.alignment_agent.run_samtools_sort_index", return_value=_mock_samtools()),
        patch("src.agents.specialists.quantification_agent.run_htseq_count", return_value=_mock_htseq()),
        patch("src.agents.specialists.de_agent.run_deseq2", return_value=_mock_deseq2()),
        patch("src.agents.specialists.de_agent._read_deseq2_file", return_value=_DE_CSV),
        patch("src.agents.specialists.gsea_agent.run_reactome_gsea", return_value=_mock_gsea()),
        patch("src.agents.specialists.gsea_agent._read_gsea_file", return_value=_GSEA_CSV),
    ):
        QCAgent(db).run(_qc_input())
        AlignmentAgent(db).run(_align_input())
        QuantificationAgent(db).run(_quant_input())
        DEAgent(db).run(_de_input())
        GSEAAgent(db).run(_gsea_input())

    assert all(r.contrast == "treatment_vs_control" for r in db.query(DEGResult).all())
    assert all(r.contrast == "treatment_vs_control" for r in db.query(GSEAResult).all())
