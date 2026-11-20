"""Tests for prepare_streamlit_data, generate_ucsc_tracks and compile_report."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.stage_inputs import REPORT_TEMPLATE
from src.tools.base import ToolValidationError
from src.tools.report.compile import ReportInput, compile_report
from src.tools.viz.streamlit_prep import StreamlitDataPrepInput, prepare_streamlit_data
from src.tools.viz.ucsc_tracks import UCSCTrackInput, generate_ucsc_tracks

DE_HEADER = "gene_id,baseMean,log2FoldChange,lfcSE,stat,pvalue,padj\n"


def _rows(path: Path) -> list[dict]:
    with open(path) as fh:
        return list(csv.DictReader(fh))


class TestPrepareStreamlitData:
    def test_merges_contrasts_and_writes_manifest(self, tmp_path: Path) -> None:
        de = tmp_path / "de"
        de.mkdir()
        (de / "B_vs_A_results.csv").write_text(DE_HEADER + "G1,10,1.5,0.2,7,1e-5,1e-4\n")
        (de / "C_vs_A_results.csv").write_text(DE_HEADER + "G1,10,-2,0.2,-9,1e-6,1e-5\n")
        (de / "normalized_counts.csv").write_text("gene_id,s1\nG1,3\n")  # ignored
        gsea = tmp_path / "gsea" / "B_vs_A"
        gsea.mkdir(parents=True)
        (gsea / "gsea_results.csv").write_text(
            "pathway_id,pathway_name,NES,pvalue,padj\nR-1,Cell cycle,2.0,0.001,0.01\n"
        )
        qc = tmp_path / "qc.json"
        qc.write_text(json.dumps({"samples": [{"sample": "S1", "mapping_rate": 91.2}]}))

        out = prepare_streamlit_data(
            StreamlitDataPrepInput(
                run_id="r1",
                de_results_dir=str(de),
                gsea_results_dir=str(tmp_path / "gsea"),
                qc_metrics_path=str(qc),
                output_dir=str(tmp_path / "viz"),
            )
        )
        manifest = json.loads(Path(out.manifest_path).read_text())
        assert manifest["available"] == {
            "de_results": "de_results.csv",
            "gsea_results": "gsea_results.csv",
            "qc_metrics": "qc_metrics.json",
        }
        de_rows = _rows(tmp_path / "viz" / "de_results.csv")
        assert [(r["contrast"], r["log2FoldChange"]) for r in de_rows] == [
            ("B_vs_A", "1.5"),
            ("C_vs_A", "-2"),
        ]
        assert _rows(tmp_path / "viz" / "gsea_results.csv")[0]["contrast"] == "B_vs_A"

    def test_dashboard_loader_reads_output(self, tmp_path: Path) -> None:
        from src.streamlit.data_loader import load_de_results, load_manifest

        de = tmp_path / "de"
        de.mkdir()
        (de / "x_results.csv").write_text(DE_HEADER + "G1,10,1.5,0.2,7,1e-5,1e-4\n")
        prepare_streamlit_data(
            StreamlitDataPrepInput(
                run_id="r", de_results_dir=str(de), output_dir=str(tmp_path / "v")
            )
        )
        manifest = load_manifest(str(tmp_path / "v"))
        df = load_de_results(str(tmp_path / "v" / manifest["available"]["de_results"]))
        assert list(df["contrast"]) == ["x"]

    def test_empty_inputs_give_empty_manifest(self, tmp_path: Path) -> None:
        out = prepare_streamlit_data(StreamlitDataPrepInput(run_id="r", output_dir=str(tmp_path)))
        assert json.loads(Path(out.manifest_path).read_text())["available"] == {}

    def test_bad_de_header_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "x_results.csv").write_text("a,b\n1,2\n")
        with pytest.raises(ToolValidationError):
            prepare_streamlit_data(
                StreamlitDataPrepInput(
                    run_id="r", de_results_dir=str(tmp_path), output_dir=str(tmp_path / "v")
                )
            )


class TestGenerateUCSCTracks:
    def test_bamcoverage_per_bam_and_hub(self, tmp_path: Path) -> None:
        bams = []
        for name in ("S1_sorted.bam", "S2_sorted.bam"):
            (tmp_path / name).write_bytes(b"")
            (tmp_path / (name + ".bai")).write_bytes(b"")
            bams.append(str(tmp_path / name))
        with (
            patch("src.tools.viz.ucsc_tracks.run_subprocess") as run,
            patch("src.tools.viz.ucsc_tracks.detect_version", return_value="bamCoverage 3.5.5"),
        ):
            out = generate_ucsc_tracks(
                UCSCTrackInput(
                    bam_paths=bams,
                    genome_build="hg38",
                    output_dir=str(tmp_path / "tracks"),
                    track_name_prefix="my run",
                )
            )
        assert run.call_count == 2
        cmd = run.call_args_list[0].args[0]
        assert cmd[0] == "bamCoverage" and "CPM" in cmd
        assert [Path(p).name for p in out.bigwig_paths] == ["my_run_S1.bw", "my_run_S2.bw"]
        track_db = Path(out.track_hub_path).read_text()
        assert "bigDataUrl ../my_run_S1.bw" in track_db and "type bigWig" in track_db
        assert "trackDb hg38/trackDb.txt" in (tmp_path / "tracks" / "genomes.txt").read_text()
        assert out.tool_version == "bamCoverage 3.5.5"

    def test_missing_index_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "a.bam").write_bytes(b"")
        with pytest.raises(ToolValidationError):
            generate_ucsc_tracks(
                UCSCTrackInput(
                    bam_paths=[str(tmp_path / "a.bam")],
                    genome_build="hg38",
                    output_dir=str(tmp_path),
                    track_name_prefix="r",
                )
            )


class TestCompileReport:
    def test_tables_from_validated_outputs(self, tmp_path: Path) -> None:
        out = compile_report(
            ReportInput(
                run_id="r1",
                run_name="<b>trial</b>",
                qc_summary={"s1": {"summary": {"a": "PASS", "b": "WARN", "c": "PASS"}}},
                de_summary={
                    "B_vs_A": {
                        "total_genes": 100,
                        "upregulated": 7,
                        "downregulated": 3,
                        "not_significant": 90,
                    }
                },
                gsea_summary={"B_vs_A": {"significant_pathway_count": 4}},
                artifact_paths={"de_B_vs_A": "/x/y/B_vs_A_results.csv"},
                output_dir=str(tmp_path),
                template_path=REPORT_TEMPLATE,
            )
        )
        md = Path(out.markdown_report_path).read_text()
        assert "| s1 | 2 | 1 | 0 |" in md
        assert "| B_vs_A | 100 | 7 | 3 | 90 |" in md
        assert "| B_vs_A | 4 |" in md
        assert "B_vs_A_results.csv" in md and "/x/y" not in md
        page = Path(out.html_report_path).read_text()
        assert "&lt;b&gt;trial&lt;/b&gt;" in page and "<b>trial</b>" not in page
        assert "<td>7</td>" in page

    def test_missing_template_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ToolValidationError):
            compile_report(
                ReportInput(
                    run_id="r", run_name="n", output_dir=str(tmp_path), template_path="/nope"
                )
            )
