"""Pathway Enrichment page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.streamlit.components.pathway_bubble import make_pathway_bubble
from src.streamlit.data_loader import load_gsea_results, load_manifest


def render(data_dir: str) -> None:
    st.header("Pathway Enrichment")

    try:
        manifest = load_manifest(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    gsea_rel = manifest.get("available", {}).get("gsea_results")
    if not gsea_rel:
        st.info("No GSEA results available for this run.")
        return

    df = load_gsea_results(str(Path(data_dir) / gsea_rel))

    # ── Sidebar filters ───────────────────────────────────────────────────────
    padj_cutoff = st.sidebar.slider("padj cutoff", 0.001, 0.5, 0.05, 0.001,
                                    format="%.3f")
    top_n = st.sidebar.slider("Top N pathways", 5, 50, 20, 5)

    sig = df[df["padj"] <= padj_cutoff]
    st.metric("Significant pathways (padj ≤ cutoff)", len(sig))

    st.subheader("Enrichment Bubble Chart")
    st.plotly_chart(
        make_pathway_bubble(df, top_n=top_n, padj_cutoff=padj_cutoff),
        use_container_width=True,
    )

    st.subheader("Results Table")
    st.dataframe(sig.sort_values("padj"), use_container_width=True)
