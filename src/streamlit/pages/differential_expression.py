"""Differential Expression page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.streamlit.components.heatmap import make_heatmap
from src.streamlit.components.ma_plot import make_ma_plot
from src.streamlit.components.volcano_plot import make_volcano_plot
from src.streamlit.data_loader import load_de_results, load_manifest


def render(data_dir: str) -> None:
    st.header("Differential Expression")

    try:
        manifest = load_manifest(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    de_rel = manifest.get("available", {}).get("de_results")
    if not de_rel:
        st.info("No DE results available for this run.")
        return

    df = load_de_results(str(Path(data_dir) / de_rel))

    # ── Sidebar filters ───────────────────────────────────────────────────────
    contrasts = sorted(df["contrast"].unique()) if "contrast" in df.columns else ["all"]
    contrast = st.sidebar.selectbox("Contrast", contrasts)
    if "contrast" in df.columns:
        df = df[df["contrast"] == contrast]

    padj_cutoff = st.sidebar.slider("padj cutoff", 0.001, 0.5, 0.05, 0.001,
                                    format="%.3f")
    lfc_cutoff = st.sidebar.slider("LFC cutoff (|log₂FC|)", 0.0, 4.0, 1.0, 0.1)
    top_n = st.sidebar.slider("Top N genes (heatmap)", 10, 100, 50, 10)

    # ── Metrics ───────────────────────────────────────────────────────────────
    n_sig = int((df["padj"] <= padj_cutoff).sum())
    st.metric("Significant genes (padj ≤ cutoff)", n_sig)

    # ── Plots ──────────────────────────────────────────────────────────────────
    st.subheader("Volcano Plot")
    st.plotly_chart(
        make_volcano_plot(df, padj_cutoff=padj_cutoff, lfc_cutoff=lfc_cutoff),
        use_container_width=True,
    )

    st.subheader("MA Plot")
    st.plotly_chart(make_ma_plot(df, padj_cutoff=padj_cutoff), use_container_width=True)

    st.subheader("Heatmap — Top DE Genes")
    st.plotly_chart(make_heatmap(df, top_n=top_n), use_container_width=True)

    # ── Results table ─────────────────────────────────────────────────────────
    st.subheader("Results Table")
    st.dataframe(
        df[df["padj"] <= padj_cutoff].sort_values("padj"),
        use_container_width=True,
    )
