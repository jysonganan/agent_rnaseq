"""Tests for Plotly component functions — no Streamlit context needed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.streamlit.components.heatmap import make_heatmap
from src.streamlit.components.ma_plot import make_ma_plot
from src.streamlit.components.pathway_bubble import make_pathway_bubble
from src.streamlit.components.qc_metrics_table import make_qc_table
from src.streamlit.components.umap_plot import make_umap_plot
from src.streamlit.components.volcano_plot import make_volcano_plot
from src.streamlit.data_loader import load_de_results, load_gsea_results, load_qc_metrics

FIXTURES = Path(__file__).parent / "fixtures"


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def de_df() -> pd.DataFrame:
    return load_de_results(str(FIXTURES / "de_results.csv"))


@pytest.fixture(scope="module")
def gsea_df() -> pd.DataFrame:
    return load_gsea_results(str(FIXTURES / "gsea_results.csv"))


@pytest.fixture(scope="module")
def qc_metrics() -> dict:
    return load_qc_metrics(str(FIXTURES / "qc_metrics.json"))


@pytest.fixture(scope="module")
def umap_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 200
    return pd.DataFrame(
        {
            "UMAP1": rng.standard_normal(n),
            "UMAP2": rng.standard_normal(n),
            "cluster": rng.integers(0, 5, n),
        }
    )


# ── Volcano plot ──────────────────────────────────────────────────────────────


def test_volcano_plot_returns_figure(de_df):
    import plotly.graph_objects as go

    fig = make_volcano_plot(de_df)
    assert isinstance(fig, go.Figure)


def test_volcano_plot_has_traces(de_df):
    fig = make_volcano_plot(de_df)
    assert len(fig.data) > 0


def test_volcano_plot_axes_titles(de_df):
    fig = make_volcano_plot(de_df)
    assert fig.layout.xaxis.title.text is not None
    assert fig.layout.yaxis.title.text is not None


def test_volcano_padj_cutoff_reduces_significant_count(de_df):
    """Stricter padj cutoff should produce fewer significant points."""

    def count_sig_points(fig) -> int:
        return sum(
            len(t.x)
            for t in fig.data
            if t.name is not None and "Significant" in t.name and t.name != "Not significant"
        )

    strict_fig = make_volcano_plot(de_df, padj_cutoff=0.001, lfc_cutoff=0.5)
    loose_fig = make_volcano_plot(de_df, padj_cutoff=0.3, lfc_cutoff=0.5)
    assert count_sig_points(strict_fig) < count_sig_points(loose_fig)


def test_volcano_not_significant_trace_present(de_df):
    fig = make_volcano_plot(de_df)
    names = [t.name for t in fig.data]
    assert "Not significant" in names


# ── MA plot ───────────────────────────────────────────────────────────────────


def test_ma_plot_returns_figure(de_df):
    import plotly.graph_objects as go

    fig = make_ma_plot(de_df)
    assert isinstance(fig, go.Figure)


def test_ma_plot_has_traces(de_df):
    fig = make_ma_plot(de_df)
    assert len(fig.data) > 0


def test_ma_plot_axes_titles(de_df):
    fig = make_ma_plot(de_df)
    assert fig.layout.xaxis.title.text is not None
    assert fig.layout.yaxis.title.text is not None


def test_ma_plot_total_points_equals_input_rows(de_df):
    fig = make_ma_plot(de_df)
    total_points = sum(len(t.x) for t in fig.data)
    assert total_points == len(de_df)


# ── Heatmap ───────────────────────────────────────────────────────────────────


def test_heatmap_returns_figure(de_df):
    import plotly.graph_objects as go

    fig = make_heatmap(de_df)
    assert isinstance(fig, go.Figure)


def test_heatmap_has_traces(de_df):
    fig = make_heatmap(de_df)
    assert len(fig.data) > 0


def test_heatmap_top_n_limits_rows(de_df):
    top_n = 3
    fig = make_heatmap(de_df, top_n=top_n)
    heatmap_trace = fig.data[0]
    assert len(heatmap_trace.z) <= top_n


def test_heatmap_full_top_n_within_dataset(de_df):
    fig = make_heatmap(de_df, top_n=5)
    assert len(fig.data[0].z) == 5


# ── Pathway bubble chart ──────────────────────────────────────────────────────


def test_pathway_bubble_returns_figure(gsea_df):
    import plotly.graph_objects as go

    fig = make_pathway_bubble(gsea_df, padj_cutoff=1.0)
    assert isinstance(fig, go.Figure)


def test_pathway_bubble_has_traces_when_sig(gsea_df):
    fig = make_pathway_bubble(gsea_df, padj_cutoff=0.05)
    assert len(fig.data) > 0


def test_pathway_bubble_empty_when_no_sig(gsea_df):
    fig = make_pathway_bubble(gsea_df, padj_cutoff=0.0001)
    # All pathways filtered out — figure should have no data or an empty trace
    total_points = sum(len(t.x) if hasattr(t, "x") and t.x is not None else 0 for t in fig.data)
    assert total_points == 0


def test_pathway_bubble_top_n_limits_pathways(gsea_df):
    fig = make_pathway_bubble(gsea_df, top_n=2, padj_cutoff=1.0)
    total_points = sum(len(t.x) for t in fig.data if hasattr(t, "x") and t.x is not None)
    assert total_points <= 2


# ── UMAP plot ─────────────────────────────────────────────────────────────────


def test_umap_plot_returns_figure(umap_df):
    import plotly.graph_objects as go

    fig = make_umap_plot(umap_df)
    assert isinstance(fig, go.Figure)


def test_umap_plot_has_traces(umap_df):
    fig = make_umap_plot(umap_df)
    assert len(fig.data) > 0


def test_umap_plot_one_trace_per_cluster(umap_df):
    n_clusters = umap_df["cluster"].nunique()
    fig = make_umap_plot(umap_df, color_col="cluster")
    assert len(fig.data) == n_clusters


def test_umap_plot_total_points_equals_cells(umap_df):
    fig = make_umap_plot(umap_df, color_col="cluster")
    total = sum(len(t.x) for t in fig.data)
    assert total == len(umap_df)


# ── QC metrics table ──────────────────────────────────────────────────────────


def test_qc_table_returns_figure(qc_metrics):
    import plotly.graph_objects as go

    fig = make_qc_table(qc_metrics)
    assert isinstance(fig, go.Figure)


def test_qc_table_has_traces(qc_metrics):
    fig = make_qc_table(qc_metrics)
    assert len(fig.data) > 0


def test_qc_table_empty_metrics_returns_figure():
    import plotly.graph_objects as go

    fig = make_qc_table({"samples": []})
    assert isinstance(fig, go.Figure)


def test_qc_table_sample_ids_in_cells(qc_metrics):
    fig = make_qc_table(qc_metrics)
    table = fig.data[0]
    # cells.values is a tuple of column lists; flatten to find sample IDs
    all_values = [str(v) for col in table.cells.values for v in col]
    assert "S1_treated" in all_values
    assert "S2_control" in all_values
