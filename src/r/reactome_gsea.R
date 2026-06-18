#!/usr/bin/env Rscript
# Reactome Gene Set Enrichment Analysis using fgsea
#
# Usage:
#   Rscript --vanilla reactome_gsea.R \
#       <de_results_path> <organism> <output_dir> \
#       [rank_metric=stat] [nperm=1000]
#
# Arguments are positional CLI values — no R code is accepted or eval()'d.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) == 0 || "--help" %in% args || "-h" %in% args) {
  cat("Usage: Rscript reactome_gsea.R <de_results_path> <organism> <output_dir>",
      "[rank_metric] [nperm]\n")
  cat("  de_results_path : Path to DESeq2 results CSV\n")
  cat("  organism        : human or mouse\n")
  cat("  output_dir      : Directory for output files\n")
  cat("  rank_metric     : stat (default) or log2fc_signed\n")
  cat("  nperm           : Number of permutations (default: 1000, range: 100-10000)\n")
  quit(status = 0)
}

if (length(args) < 3) {
  cat("Error: at least 3 positional arguments are required. Use --help for usage.\n",
      file = stderr())
  quit(status = 1)
}

de_results_path <- args[1]
organism        <- args[2]
output_dir      <- args[3]
rank_metric     <- if (length(args) >= 4) args[4] else "stat"
nperm           <- if (length(args) >= 5) as.integer(args[5]) else 1000L

# Validate inputs — no eval() on any argument
if (!file.exists(de_results_path)) {
  cat(sprintf("Error: de_results_path not found: %s\n", de_results_path), file = stderr())
  quit(status = 1)
}
if (!organism %in% c("human", "mouse")) {
  cat("Error: organism must be 'human' or 'mouse'\n", file = stderr())
  quit(status = 1)
}
if (!rank_metric %in% c("stat", "log2fc_signed")) {
  cat("Error: rank_metric must be 'stat' or 'log2fc_signed'\n", file = stderr())
  quit(status = 1)
}
if (is.na(nperm) || nperm < 100L || nperm > 10000L) {
  cat("Error: nperm must be in [100, 10000]\n", file = stderr())
  quit(status = 1)
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
plots_dir <- file.path(output_dir, "plots")
dir.create(plots_dir, recursive = TRUE, showWarnings = FALSE)

suppressPackageStartupMessages({
  library(fgsea)
  library(reactome.db)
  library(AnnotationDbi)
})

# Select organism annotation package
if (organism == "human") {
  suppressPackageStartupMessages(library(org.Hs.eg.db))
  org_db <- org.Hs.eg.db
} else {
  suppressPackageStartupMessages(library(org.Mm.eg.db))
  org_db <- org.Mm.eg.db
}

# Read DE results
de_res <- read.csv(de_results_path)

# Build ranked gene list
if (rank_metric == "stat") {
  rank_values <- setNames(de_res$stat, de_res$gene_id)
} else {
  rank_values <- setNames(
    sign(de_res$log2FoldChange) * (-log10(de_res$pvalue + 1e-300)),
    de_res$gene_id
  )
}
rank_values <- sort(rank_values[!is.na(rank_values)], decreasing = TRUE)

# Map gene symbols to Entrez IDs
entrez_map <- mapIds(
  org_db,
  keys      = names(rank_values),
  column    = "ENTREZID",
  keytype   = "SYMBOL",
  multiVals = "first"
)
entrez_map   <- entrez_map[!is.na(entrez_map)]
ranks_entrez <- rank_values[names(entrez_map)]
names(ranks_entrez) <- unname(entrez_map)

# Reactome pathway gene sets
pathways <- reactomePathways(names(ranks_entrez))

# Run fgsea
set.seed(42)
fgsea_res <- fgsea(
  pathways = pathways,
  stats    = ranks_entrez,
  nperm    = nperm
)

# Format and write output
out_df <- data.frame(
  pathway_id   = fgsea_res$pathway,
  pathway_name = fgsea_res$pathway,
  NES          = fgsea_res$NES,
  pvalue       = fgsea_res$pval,
  padj         = fgsea_res$padj,
  stringsAsFactors = FALSE
)
out_df <- out_df[order(out_df$padj), ]

write.csv(out_df, file.path(output_dir, "gsea_results.csv"), row.names = FALSE)

cat("Reactome GSEA complete.\n")
