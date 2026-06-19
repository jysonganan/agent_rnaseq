#!/usr/bin/env python
"""Scanpy single-cell preprocessing, clustering, and UMAP pipeline.

Usage::

    python scanpy_pipeline.py \\
        --matrix-dir /path/to/filtered_feature_bc_matrix \\
        --output-dir /path/to/output \\
        [--min-genes 200] [--min-cells 3] [--max-pct-mt 20.0] \\
        [--n-top-genes 2000] [--n-neighbors 15]

All arguments are positional flags — no Python code is accepted or eval()'d.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scanpy scRNA-seq preprocessing, clustering, and UMAP pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--matrix-dir",
        required=True,
        help="Path to CellRanger filtered_feature_bc_matrix directory.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for output files (created if absent).",
    )
    parser.add_argument(
        "--min-genes",
        type=int,
        default=200,
        help="Minimum number of genes expressed per cell (QC threshold).",
    )
    parser.add_argument(
        "--min-cells",
        type=int,
        default=3,
        help="Minimum number of cells a gene must appear in (QC threshold).",
    )
    parser.add_argument(
        "--max-pct-mt",
        type=float,
        default=20.0,
        help="Maximum percentage of mitochondrial reads per cell (QC threshold, 5–50).",
    )
    parser.add_argument(
        "--n-top-genes",
        type=int,
        default=2000,
        help="Number of highly variable genes to select.",
    )
    parser.add_argument(
        "--n-neighbors",
        type=int,
        default=15,
        help="Number of neighbours for the kNN graph (UMAP/clustering).",
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not os.path.isdir(args.matrix_dir):
        print(f"Error: --matrix-dir not found: {args.matrix_dir}", file=sys.stderr)
        sys.exit(1)
    if not (5.0 <= args.max_pct_mt <= 50.0):
        print("Error: --max-pct-mt must be in [5.0, 50.0]", file=sys.stderr)
        sys.exit(1)
    if args.min_genes < 1:
        print("Error: --min-genes must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.min_cells < 1:
        print("Error: --min-cells must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.n_neighbors < 2:
        print("Error: --n-neighbors must be >= 2", file=sys.stderr)
        sys.exit(1)


def run_pipeline(args: argparse.Namespace) -> None:
    import scanpy as sc

    os.makedirs(args.output_dir, exist_ok=True)

    # ── Load data ────────────────────────────────────────────────────────────
    adata = sc.read_10x_mtx(args.matrix_dir, var_names="gene_symbols", cache=False)
    adata.var_names_make_unique()

    # ── QC filtering ─────────────────────────────────────────────────────────
    adata.var["mt"] = adata.var_names.str.startswith("MT-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True)
    adata = adata[adata.obs.n_genes_by_counts >= args.min_genes, :]
    adata = adata[adata.obs.pct_counts_mt < args.max_pct_mt, :]
    sc.pp.filter_genes(adata, min_cells=args.min_cells)

    # ── Normalisation & HVG selection ────────────────────────────────────────
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=args.n_top_genes)
    adata = adata[:, adata.var.highly_variable]

    # ── Dimensionality reduction & clustering ────────────────────────────────
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, svd_solver="arpack")
    sc.pp.neighbors(adata, n_neighbors=args.n_neighbors, n_pcs=40)
    sc.tl.umap(adata)
    sc.tl.leiden(adata)

    # ── Marker genes ─────────────────────────────────────────────────────────
    sc.tl.rank_genes_groups(adata, "leiden", method="wilcoxon")

    # ── Write outputs ────────────────────────────────────────────────────────
    h5ad_path = os.path.join(args.output_dir, "cells.h5ad")
    adata.write(h5ad_path)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sc.pl.umap(adata, color="leiden", show=False)
    plt.savefig(os.path.join(args.output_dir, "umap.pdf"), bbox_inches="tight")
    plt.close()

    marker_df = sc.get.rank_genes_groups_df(adata, group=None)
    marker_df.to_csv(os.path.join(args.output_dir, "marker_genes.csv"), index=False)

    clusters = sorted(adata.obs["leiden"].unique(), key=int)
    cells_per_cluster = {c: int((adata.obs["leiden"] == c).sum()) for c in clusters}
    cluster_summary = {
        "n_clusters": len(clusters),
        "cells_per_cluster": cells_per_cluster,
    }
    with open(os.path.join(args.output_dir, "cluster_summary.json"), "w") as fh:
        json.dump(cluster_summary, fh, indent=2)

    print(f"Scanpy pipeline complete: {len(clusters)} clusters, {adata.n_obs} cells retained.")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    validate_args(args)
    run_pipeline(args)


if __name__ == "__main__":
    main()
