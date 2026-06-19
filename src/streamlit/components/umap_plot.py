"""UMAP scatter plot component for single-cell data."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def make_umap_plot(
    df: pd.DataFrame,
    color_col: str = "cluster",
) -> go.Figure:
    """Return an interactive UMAP scatter coloured by *color_col*."""
    fig = go.Figure()

    if color_col in df.columns:
        for label in sorted(df[color_col].unique()):
            sub = df[df[color_col] == label]
            fig.add_trace(
                go.Scatter(
                    x=sub["UMAP1"],
                    y=sub["UMAP2"],
                    mode="markers",
                    name=str(label),
                    marker=dict(size=4, opacity=0.7),
                    hovertemplate=f"Cluster {label}<br>(%{{x:.2f}}, %{{y:.2f}})<extra></extra>",
                )
            )
    else:
        fig.add_trace(
            go.Scatter(
                x=df["UMAP1"],
                y=df["UMAP2"],
                mode="markers",
                marker=dict(size=4, opacity=0.7),
                name="cells",
            )
        )

    fig.update_layout(
        title="Single-Cell UMAP",
        xaxis_title="UMAP 1",
        yaxis_title="UMAP 2",
        legend_title=color_col,
    )
    return fig
