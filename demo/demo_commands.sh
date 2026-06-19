#!/usr/bin/env bash
# demo_commands.sh — shell script for the agent_rnaseq video demo
#
# Records a self-contained terminal session showing:
#   install → data prep → run notebook → Streamlit viewer
#
# Record with asciinema:
#   asciinema rec demo/demo.cast --command bash demo/demo_commands.sh
#
# Convert to GIF:
#   agg demo/demo.cast demo/demo.gif --cols 120 --rows 35
#
# Convert to MP4 (requires agg + ffmpeg):
#   agg demo/demo.cast demo/demo.gif && ffmpeg -i demo/demo.gif demo/demo.mp4

set -euo pipefail

# ─── helpers ─────────────────────────────────────────────────────────────────

BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RESET="\033[0m"

banner()  { echo -e "\n${BOLD}${CYAN}═══ $* ═══${RESET}\n"; }
step()    { echo -e "${BOLD}${GREEN}▶ $*${RESET}"; }
note()    { echo -e "${YELLOW}# $*${RESET}"; sleep 0.4; }
pause()   { sleep "${1:-1}"; }

# Slow-type effect (makes terminal recordings readable)
type_cmd() {
    local cmd="$*"
    echo -ne "${BOLD}\$ ${RESET}"
    for ((i=0; i<${#cmd}; i++)); do
        printf '%s' "${cmd:$i:1}"
        sleep 0.04
    done
    echo
    pause 0.6
    eval "$cmd"
}

# ─── check prereqs ────────────────────────────────────────────────────────────

banner "agent_rnaseq  End-to-End Pipeline Demo"
pause 1

step "Checking prerequisites"
python --version
docker --version 2>/dev/null || echo "(Docker not required for notebook demo)"
pause 1

# ─── installation ─────────────────────────────────────────────────────────────

banner "Step 1 — Installation"

note "Clone the repository"
type_cmd "git clone https://github.com/jysonganan/agent_rnaseq.git"
type_cmd "cd agent_rnaseq"

note "Install Python package and dev dependencies"
type_cmd "pip install -e '.[dev]' -q"
echo -e "${GREEN}✓ Package installed${RESET}"
pause 1

# ─── data preparation ─────────────────────────────────────────────────────────

banner "Step 2 — Synthetic Demo Data"

note "Generate 8 synthetic FASTQ files (4 samples × paired-end)"
type_cmd "python data/generate_data.py"
pause 1

note "Verify files"
type_cmd "ls -lh data/*.fastq.gz"
pause 1

# ─── run notebook non-interactively ──────────────────────────────────────────

banner "Step 3 — Run the Pipeline Agent"

note "Execute demo notebook (jupyter nbconvert runs all cells)"
type_cmd "jupyter nbconvert --to notebook --execute --inplace notebooks/demo.ipynb --ExecutePreprocessor.timeout=120"
echo -e "${GREEN}✓ Notebook executed successfully${RESET}"
pause 1

note "Check generated output"
type_cmd "ls -lh demo_output/streamlit_data/"
pause 1

# ─── show results inline ──────────────────────────────────────────────────────

banner "Step 4 — Results Summary"

note "Significant DE genes"
python - <<'PYEOF'
import pandas as pd
df = pd.read_csv("demo_output/streamlit_data/de_results.csv")
sig = df[df["padj"] <= 0.05]
print(f"  Total genes     : {len(df):>5,}")
print(f"  Significant     : {len(sig):>5,}  (padj ≤ 0.05)")
print(f"  Up-regulated    : {int(((sig['log2FoldChange'] > 1)).sum()):>5,}  (|LFC| > 1)")
print(f"  Down-regulated  : {int(((sig['log2FoldChange'] < -1)).sum()):>5,}  (|LFC| > 1)")
print()
print("Top 5 genes by adjusted p-value:")
print(sig.sort_values("padj")[["gene_name","log2FoldChange","padj"]].head(5).to_string(index=False))
PYEOF
pause 1

note "Top GSEA pathways"
python - <<'PYEOF'
import pandas as pd
df = pd.read_csv("demo_output/streamlit_data/gsea_results.csv")
sig = df[df["padj"] <= 0.25].sort_values("padj")
print(f"  Pathways tested : {len(df):>5,}")
print(f"  Significant     : {len(sig):>5,}  (padj ≤ 0.25)")
print()
print("Top 5 pathways:")
print(sig[["pathway_name","NES","padj"]].head(5).to_string(index=False))
PYEOF
pause 1

# ─── streamlit ────────────────────────────────────────────────────────────────

banner "Step 5 — Launch Streamlit Dashboard"

DATA_DIR="$(pwd)/demo_output/streamlit_data"
note "Starting Streamlit — will be available at http://localhost:8501"
echo -e "${BOLD}STREAMLIT_DATA_DIR=${DATA_DIR} streamlit run src/streamlit/app.py${RESET}"
echo
echo -e "${GREEN}Open your browser at: http://localhost:8501${RESET}"
echo -e "${YELLOW}Set 'Data directory' in the sidebar to:${RESET}"
echo -e "  ${DATA_DIR}"
echo
echo -e "${YELLOW}Available pages:${RESET}"
echo "  📊 QC Dashboard        — mapping rates, GC content, duplication"
echo "  🔬 Differential Expr.  — volcano plot, MA plot, heatmap, DE table"
echo "  🧬 Pathway Enrichment  — Reactome GSEA bubble chart"
echo
note "Starting Streamlit in background (Ctrl+C to stop)"
STREAMLIT_DATA_DIR="${DATA_DIR}" streamlit run src/streamlit/app.py \
    --server.headless=true \
    --server.port=8501 &
STPID=$!
echo -e "${GREEN}✓ Streamlit PID: ${STPID}${RESET}"
pause 5

echo
banner "Demo Complete"
echo -e "${GREEN}✓ All pipeline stages completed via OrchestratorAgent (LangGraph)${RESET}"
echo -e "${GREEN}✓ Results written to demo_output/streamlit_data/${RESET}"
echo -e "${GREEN}✓ Streamlit running at http://localhost:8501${RESET}"
echo
echo "Press Ctrl+C or close the terminal to stop Streamlit."
wait $STPID 2>/dev/null || true
