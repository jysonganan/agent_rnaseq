"""Heatmap component: log2FoldChange for top-N most significant genes."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def make_heatmap(
    df: pd.DataFrame,
    top_n: int = 50,
) -> go.Figure:
    """Return a heatmap of log2FoldChange for the *top_n* most significant genes."""
    df = df.dropna(subset=["padj", "log2FoldChange"]).sort_values("padj").head(top_n)
    label_col = "gene_name" if "gene_name" in df.columns else "gene_id"
    labels = df[label_col].tolist()
    values = df["log2FoldChange"].tolist()

    fig = go.Figure(
        data=go.Heatmap(
            z=[[v] for v in values],
            y=labels,
            x=["log₂FC"],
            colorscale="RdBu_r",
            zmid=0,
            colorbar=dict(title="log₂FC"),
        )
    )
    fig.update_layout(
        title=f"Top {len(labels)} DE Genes — log₂ Fold Change",
        height=max(400, len(labels) * 14),
        yaxis=dict(autorange="reversed"),
    )
    return fig
