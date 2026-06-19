"""MA plot component: log10(baseMean) vs log2FoldChange."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def make_ma_plot(
    df: pd.DataFrame,
    padj_cutoff: float = 0.05,
) -> go.Figure:
    """Return an interactive MA plot for DE results."""
    df = df.copy()
    df["_log10_mean"] = np.log10(df["baseMean"].clip(lower=0.01))
    df["_sig"] = df["padj"] <= padj_cutoff
    label_col = "gene_name" if "gene_name" in df.columns else "gene_id"

    fig = go.Figure()
    for is_sig, colour, name in [
        (False, "lightgray", "Not significant"),
        (True, "crimson", "Significant"),
    ]:
        sub = df[df["_sig"] == is_sig]
        fig.add_trace(
            go.Scatter(
                x=sub["_log10_mean"],
                y=sub["log2FoldChange"],
                mode="markers",
                marker=dict(color=colour, size=5, opacity=0.75),
                name=name,
                text=sub[label_col],
                hovertemplate="%{text}<br>log10(mean)=%{x:.2f}<br>LFC=%{y:.3f}<extra></extra>",
            )
        )

    fig.add_hline(y=0, line_dash="solid", line_color="black", line_width=1, opacity=0.4)
    fig.update_layout(
        title="MA Plot",
        xaxis_title="log₁₀(baseMean)",
        yaxis_title="log₂ Fold Change",
        legend_title="Category",
    )
    return fig
