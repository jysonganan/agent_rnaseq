"""QC metrics table component."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def make_qc_table(metrics: dict) -> go.Figure:
    """Return a Plotly Table figure from the QC metrics dict."""
    samples = metrics.get("samples", [])
    if not samples:
        fig = go.Figure()
        fig.update_layout(title="No QC metrics available")
        return fig

    df = pd.DataFrame(samples)
    fig = go.Figure(
        data=go.Table(
            header=dict(
                values=[f"<b>{c}</b>" for c in df.columns],
                fill_color="steelblue",
                font=dict(color="white", size=12),
                align="left",
            ),
            cells=dict(
                values=[df[c].tolist() for c in df.columns],
                fill_color="lavender",
                align="left",
            ),
        )
    )
    fig.update_layout(title="QC Metrics per Sample")
    return fig
