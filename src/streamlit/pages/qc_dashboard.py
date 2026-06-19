"""QC Dashboard page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from src.streamlit.components.qc_metrics_table import make_qc_table
from src.streamlit.data_loader import load_manifest, load_qc_metrics


def render(data_dir: str) -> None:
    st.header("QC Dashboard")

    try:
        manifest = load_manifest(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    qc_rel = manifest.get("available", {}).get("qc_metrics")
    if not qc_rel:
        st.info("No QC metrics available for this run.")
        return

    metrics = load_qc_metrics(str(Path(data_dir) / qc_rel))
    samples = metrics.get("samples", [])

    if samples:
        c1, c2, c3 = st.columns(3)
        c1.metric("Samples", len(samples))
        avg_rate = sum(s.get("mapping_rate", 0) for s in samples) / len(samples)
        c2.metric("Avg Mapping Rate", f"{avg_rate:.1f}%")
        avg_reads = sum(s.get("total_reads", 0) for s in samples) / len(samples)
        c3.metric("Avg Total Reads", f"{avg_reads:,.0f}")

    st.subheader("Sample QC Table")
    fig = make_qc_table(metrics)
    st.plotly_chart(fig, use_container_width=True)
