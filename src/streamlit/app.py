"""RNA-seq Agent Streamlit dashboard — main entry point."""

from __future__ import annotations

import os

import streamlit as st

from src.streamlit.pages import (
    differential_expression,
    pathway_enrichment,
    qc_dashboard,
    single_cell,
)

_DEFAULT_DATA_DIR = os.environ.get("STREAMLIT_DATA_DIR", "/tmp/streamlit_data")

st.set_page_config(
    page_title="RNA-seq Agent Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("RNA-seq Agent")
st.sidebar.markdown("---")
data_dir: str = st.sidebar.text_input(
    "Data directory",
    value=_DEFAULT_DATA_DIR,
    key="data_dir",
    help="Path to the streamlit_data/ directory produced by prepare_streamlit_data.",
)
st.sidebar.markdown("---")


def _render_qc() -> None:
    qc_dashboard.render(st.session_state.get("data_dir", _DEFAULT_DATA_DIR))


def _render_de() -> None:
    differential_expression.render(st.session_state.get("data_dir", _DEFAULT_DATA_DIR))


def _render_pathway() -> None:
    pathway_enrichment.render(st.session_state.get("data_dir", _DEFAULT_DATA_DIR))


def _render_sc() -> None:
    single_cell.render(st.session_state.get("data_dir", _DEFAULT_DATA_DIR))


pg = st.navigation(
    [
        st.Page(_render_qc, title="QC Dashboard", icon="📊"),
        st.Page(_render_de, title="Differential Expression", icon="🔬"),
        st.Page(_render_pathway, title="Pathway Enrichment", icon="🧬"),
        st.Page(_render_sc, title="Single Cell", icon="🔭"),
    ]
)
pg.run()
