"""Single-Cell Analysis page."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import streamlit as st
from src.streamlit.components.umap_plot import make_umap_plot
from src.streamlit.data_loader import load_manifest


def render(data_dir: str) -> None:
    st.header("Single-Cell Analysis")

    try:
        manifest = load_manifest(data_dir)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    sc_rel = manifest.get("available", {}).get("sc_umap")
    if not sc_rel:
        st.info("No single-cell UMAP data available for this run.")
        return

    df = pd.read_csv(str(Path(data_dir) / sc_rel))

    colour_opts = df.columns.tolist()
    colour_col = st.sidebar.selectbox(
        "Colour by",
        colour_opts,
        index=colour_opts.index("cluster") if "cluster" in colour_opts else 0,
    )

    c1, c2 = st.columns(2)
    c1.metric("Total cells", len(df))
    if "cluster" in df.columns:
        c2.metric("Clusters", df["cluster"].nunique())

    st.subheader("UMAP")
    st.plotly_chart(make_umap_plot(df, color_col=colour_col), use_container_width=True)

    if "marker_gene" in df.columns:
        st.subheader("Marker Genes")
        st.dataframe(df[["cluster", "marker_gene"]].drop_duplicates(), use_container_width=True)
