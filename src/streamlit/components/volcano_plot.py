"""Volcano plot component: log2FoldChange vs -log10(padj)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def make_volcano_plot(
    df: pd.DataFrame,
    padj_cutoff: float = 0.05,
    lfc_cutoff: float = 1.0,
) -> go.Figure:
    """Return an interactive volcano plot for DE results.

    Colours: up-regulated significant → red, down-regulated significant → blue,
    not significant → grey.
    """
    df = df.copy()
    df["_neg_log10_padj"] = -np.log10(df["padj"].clip(lower=1e-300))

    def _cat(row: pd.Series) -> str:
        if row["padj"] <= padj_cutoff and row["log2FoldChange"] >= lfc_cutoff:
            return "Significant (up)"
        if row["padj"] <= padj_cutoff and row["log2FoldChange"] <= -lfc_cutoff:
            return "Significant (down)"
        return "Not significant"

    df["_cat"] = df.apply(_cat, axis=1)
    label_col = "gene_name" if "gene_name" in df.columns else "gene_id"

    colour_map = {
        "Significant (up)": "crimson",
        "Significant (down)": "steelblue",
        "Not significant": "lightgray",
    }

    fig = go.Figure()
    for cat, colour in colour_map.items():
        mask = df["_cat"] == cat
        sub = df[mask]
        fig.add_trace(
            go.Scatter(
                x=sub["log2FoldChange"],
                y=sub["_neg_log10_padj"],
                mode="markers",
                marker=dict(color=colour, size=5, opacity=0.75),
                name=cat,
                text=sub[label_col],
                hovertemplate="%{text}<br>LFC=%{x:.3f}<br>−log10(padj)=%{y:.2f}<extra></extra>",
            )
        )

    fig.add_vline(x=lfc_cutoff, line_dash="dot", line_color="gray", opacity=0.5)
    fig.add_vline(x=-lfc_cutoff, line_dash="dot", line_color="gray", opacity=0.5)
    fig.add_hline(
        y=-np.log10(padj_cutoff), line_dash="dot", line_color="gray", opacity=0.5
    )

    fig.update_layout(
        title="Volcano Plot",
        xaxis_title="log₂ Fold Change",
        yaxis_title="−log₁₀(padj)",
        legend_title="Category",
    )
    return fig
