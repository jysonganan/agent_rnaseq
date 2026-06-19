"""Load Streamlit-ready data files produced by prepare_streamlit_data."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_manifest(data_dir: str) -> dict:
    """Return parsed manifest.json from *data_dir*.

    Raises:
        FileNotFoundError: if manifest.json is absent (clear user-facing message).
    """
    path = Path(data_dir) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"manifest.json not found in {data_dir!r}. "
            "Run the pipeline and call prepare_streamlit_data to generate the data files."
        )
    with open(path) as fh:
        return json.load(fh)


def load_de_results(path: str) -> pd.DataFrame:
    """Read a DESeq2 results CSV and return a DataFrame."""
    return pd.read_csv(path)


def load_gsea_results(path: str) -> pd.DataFrame:
    """Read a GSEA/Reactome results CSV and return a DataFrame."""
    return pd.read_csv(path)


def load_qc_metrics(path: str) -> dict:
    """Read a QC metrics JSON and return a dict."""
    with open(path) as fh:
        return json.load(fh)
