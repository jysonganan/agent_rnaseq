#!/usr/bin/env Rscript
# DESeq2 differential expression analysis
#
# Usage:
#   Rscript --vanilla deseq2_analysis.R \
#       <counts_path> <metadata_path> <contrast_name> \
#       <numerator> <denominator> <output_dir> \
#       [alpha=0.05] [lfc_threshold=0.0] [min_count=10]
#
# Arguments are positional CLI values — no R code is accepted or eval()'d.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) == 0 || "--help" %in% args || "-h" %in% args) {
  cat("Usage: Rscript deseq2_analysis.R <counts_path> <metadata_path>",
      "<contrast_name> <numerator> <denominator> <output_dir>",
      "[alpha] [lfc_threshold] [min_count]\n")
  cat("  counts_path    : Path to gene x sample count matrix CSV\n")
  cat("  metadata_path  : Path to sample metadata CSV (columns: sample_id, condition)\n")
  cat("  contrast_name  : Label for this contrast (used in output filenames)\n")
  cat("  numerator      : Condition to compare (numerator)\n")
  cat("  denominator    : Reference condition (denominator)\n")
  cat("  output_dir     : Directory for output files\n")
  cat("  alpha          : FDR threshold (default: 0.05, range: 0.001-0.1)\n")
  cat("  lfc_threshold  : Log2 fold change threshold (default: 0.0, range: 0.0-5.0)\n")
  cat("  min_count      : Minimum count filter (default: 10, range: 1-1000)\n")
  quit(status = 0)
}

if (length(args) < 6) {
  cat("Error: at least 6 positional arguments are required. Use --help for usage.\n",
      file = stderr())
  quit(status = 1)
}

counts_path   <- args[1]
metadata_path <- args[2]
contrast_name <- args[3]
numerator     <- args[4]
denominator   <- args[5]
output_dir    <- args[6]
alpha         <- if (length(args) >= 7) as.numeric(args[7]) else 0.05
lfc_threshold <- if (length(args) >= 8) as.numeric(args[8]) else 0.0
min_count     <- if (length(args) >= 9) as.integer(args[9]) else 10L

# Validate inputs — no eval() on any argument
if (!file.exists(counts_path)) {
  cat(sprintf("Error: counts_path not found: %s\n", counts_path), file = stderr())
  quit(status = 1)
}
if (!file.exists(metadata_path)) {
  cat(sprintf("Error: metadata_path not found: %s\n", metadata_path), file = stderr())
  quit(status = 1)
}
if (is.na(alpha) || alpha < 0.001 || alpha > 0.1) {
  cat("Error: alpha must be in [0.001, 0.1]\n", file = stderr())
  quit(status = 1)
}
if (is.na(lfc_threshold) || lfc_threshold < 0.0 || lfc_threshold > 5.0) {
  cat("Error: lfc_threshold must be in [0.0, 5.0]\n", file = stderr())
  quit(status = 1)
}
if (is.na(min_count) || min_count < 1L || min_count > 1000L) {
  cat("Error: min_count must be in [1, 1000]\n", file = stderr())
  quit(status = 1)
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

suppressPackageStartupMessages({
  library(DESeq2)
})

# Read inputs
counts   <- read.csv(counts_path, row.names = 1, check.names = FALSE)
metadata <- read.csv(metadata_path, row.names = 1)

# Coerce to integer count matrix
counts_int        <- round(counts)
mode(counts_int)  <- "integer"

# Filter low-count genes
keep      <- rowSums(counts_int) >= min_count
counts_int <- counts_int[keep, , drop = FALSE]

# Build DESeqDataSet
dds <- DESeqDataSetFromMatrix(
  countData = counts_int,
  colData   = metadata,
  design    = ~ condition
)

# Run DESeq2
dds <- DESeq(dds)

# Extract results for this contrast
res <- results(
  dds,
  contrast     = c("condition", numerator, denominator),
  alpha        = alpha,
  lfcThreshold = lfc_threshold
)
res_df           <- as.data.frame(res)
res_df           <- cbind(gene_id = rownames(res_df), res_df)
rownames(res_df) <- NULL

write.csv(
  res_df,
  file.path(output_dir, paste0(contrast_name, "_results.csv")),
  row.names = FALSE
)

# Normalized counts
norm_counts           <- counts(dds, normalized = TRUE)
norm_df               <- cbind(gene_id = rownames(norm_counts), as.data.frame(norm_counts))
rownames(norm_df)     <- NULL
write.csv(norm_df, file.path(output_dir, "normalized_counts.csv"), row.names = FALSE)

# Size factors
sf_df <- data.frame(
  sample_id   = colnames(dds),
  size_factor = sizeFactors(dds)
)
write.csv(sf_df, file.path(output_dir, "size_factors.csv"), row.names = FALSE)

# Dispersion plot
pdf(file.path(output_dir, "dispersion_plot.pdf"))
plotDispEsts(dds)
invisible(dev.off())

# PCA plot
vsd <- vst(dds, blind = FALSE)
pdf(file.path(output_dir, "pca_plot.pdf"))
print(plotPCA(vsd, intgroup = "condition"))
invisible(dev.off())

cat("DESeq2 analysis complete for contrast:", contrast_name, "\n")
