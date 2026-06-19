"""Pathway enrichment bubble chart component."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def make_pathway_bubble(
    df: pd.DataFrame,
    top_n: int = 20,
    padj_cutoff: float = 0.05,
) -> go.Figure:
    """Return a bubble chart of pathway enrichment results.

    Bubble size encodes gene-set size; colour encodes -log10(padj).
    """
    sig = df[df["padj"] <= padj_cutoff].sort_values("padj").head(top_n)

    if sig.empty:
        fig = go.Figure()
        fig.update_layout(title="No significant pathways at this cutoff")
        return fig

    neg_log_padj = -np.log10(sig["padj"].clip(lower=1e-300))
    max_size = sig["size"].max()
    bubble_size = (sig["size"] / max_size * 30 + 6).tolist()

    fig = go.Figure(
        data=go.Scatter(
            x=sig["NES"],
            y=sig["pathway"],
            mode="markers",
            marker=dict(
                size=bubble_size,
                color=neg_log_padj,
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="−log₁₀(padj)"),
                line=dict(width=0.5, color="white"),
            ),
            text=sig["pathway"],
            hovertemplate=(
                "<b>%{text}</b><br>NES=%{x:.2f}<br>padj=%{customdata:.3g}<extra></extra>"
            ),
            customdata=sig["padj"],
        )
    )
    fig.update_layout(
        title="Pathway Enrichment",
        xaxis_title="Normalized Enrichment Score (NES)",
        yaxis_title="",
        yaxis=dict(autorange="reversed"),
    )
    return fig
