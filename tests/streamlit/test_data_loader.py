"""Tests for data_loader — reads fixture files, no Streamlit context needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.streamlit.data_loader import (
    load_de_results,
    load_gsea_results,
    load_manifest,
    load_qc_metrics,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── load_manifest ─────────────────────────────────────────────────────────────


def test_load_manifest_raises_for_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        load_manifest(str(tmp_path))


def test_load_manifest_raises_message_includes_dir(tmp_path):
    with pytest.raises(FileNotFoundError, match=str(tmp_path)):
        load_manifest(str(tmp_path))


def test_load_manifest_returns_dict():
    m = load_manifest(str(FIXTURES))
    assert isinstance(m, dict)


def test_load_manifest_run_id():
    m = load_manifest(str(FIXTURES))
    assert m["run_id"] == "test-run-001"


def test_load_manifest_available_keys():
    m = load_manifest(str(FIXTURES))
    available = m["available"]
    assert "de_results" in available
    assert "gsea_results" in available
    assert "qc_metrics" in available


def test_load_manifest_de_results_filename():
    m = load_manifest(str(FIXTURES))
    assert m["available"]["de_results"] == "de_results.csv"


# ── load_de_results ───────────────────────────────────────────────────────────


def test_load_de_results_returns_dataframe():
    import pandas as pd
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    assert isinstance(df, pd.DataFrame)


def test_load_de_results_has_required_columns():
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    for col in ("gene_id", "log2FoldChange", "padj", "baseMean"):
        assert col in df.columns, f"Missing column: {col}"


def test_load_de_results_row_count():
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    assert len(df) == 10


def test_load_de_results_padj_values_valid():
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    assert (df["padj"] >= 0).all()
    assert (df["padj"] <= 1).all()


# ── padj filter reduces row count ─────────────────────────────────────────────


def test_strict_padj_filter_reduces_rows():
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    strict = df[df["padj"] <= 0.001]
    loose = df[df["padj"] <= 0.5]
    assert len(strict) < len(loose)


def test_padj_cutoff_0_001_gives_three_genes():
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    assert len(df[df["padj"] <= 0.001]) == 3


def test_padj_cutoff_0_05_gives_six_genes():
    df = load_de_results(str(FIXTURES / "de_results.csv"))
    assert len(df[df["padj"] <= 0.05]) == 6


# ── load_gsea_results ─────────────────────────────────────────────────────────


def test_load_gsea_results_columns():
    df = load_gsea_results(str(FIXTURES / "gsea_results.csv"))
    for col in ("pathway", "NES", "padj", "size"):
        assert col in df.columns, f"Missing column: {col}"


def test_load_gsea_results_row_count():
    df = load_gsea_results(str(FIXTURES / "gsea_results.csv"))
    assert len(df) == 5


def test_gsea_significant_at_0_05():
    df = load_gsea_results(str(FIXTURES / "gsea_results.csv"))
    sig = df[df["padj"] <= 0.05]
    assert len(sig) == 3


# ── load_qc_metrics ───────────────────────────────────────────────────────────


def test_load_qc_metrics_returns_dict():
    m = load_qc_metrics(str(FIXTURES / "qc_metrics.json"))
    assert isinstance(m, dict)


def test_load_qc_metrics_samples_key():
    m = load_qc_metrics(str(FIXTURES / "qc_metrics.json"))
    assert "samples" in m


def test_load_qc_metrics_two_samples():
    m = load_qc_metrics(str(FIXTURES / "qc_metrics.json"))
    assert len(m["samples"]) == 2


def test_load_qc_metrics_sample_fields():
    m = load_qc_metrics(str(FIXTURES / "qc_metrics.json"))
    s = m["samples"][0]
    for field in ("sample_id", "total_reads", "mapping_rate"):
        assert field in s, f"Missing field: {field}"
