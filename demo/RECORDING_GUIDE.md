# Video Demo Recording Guide

This guide explains how to record and publish a video demo of agent_rnaseq
using free, open-source tools.

---

## Option A — asciinema (recommended, 5 minutes)

[asciinema](https://asciinema.org) records and replays terminal sessions as
lightweight text files. Cast files can be embedded in web pages or converted
to GIF/MP4.

### Install

```bash
# macOS
brew install asciinema

# Linux
pip install asciinema
```

### Record

```bash
cd /path/to/agent_rnaseq
asciinema rec demo/demo.cast \
    --title "agent_rnaseq — RNA-seq Pipeline Agent Demo" \
    --command "bash demo/demo_commands.sh" \
    --cols 120 --rows 35
```

The script runs automatically; the recording ends when the script exits.
To record manually (interactive session):

```bash
asciinema rec demo/demo.cast --cols 120 --rows 35
# ... type commands manually ...
# Press Ctrl+D to end recording
```

### Play back

```bash
asciinema play demo/demo.cast
```

### Publish to asciinema.org

```bash
asciinema upload demo/demo.cast
# Returns a URL like: https://asciinema.org/a/XXXXX
```

Embed in `README.md`:
```markdown
[![demo](https://asciinema.org/a/XXXXX.svg)](https://asciinema.org/a/XXXXX)
```

---

## Option B — Convert to GIF

Use [agg](https://github.com/asciinema/agg) (asciinema GIF generator):

```bash
# Install
brew install asciinema/asciinema/agg   # macOS
# or: cargo install --git https://github.com/asciinema/agg  (Rust)

# Convert .cast to .gif
agg demo/demo.cast demo/demo.gif \
    --cols 120 --rows 35 \
    --font-size 14 \
    --speed 1.5        # optional: speed multiplier
```

Add to `README.md`:
```markdown
![demo](demo/demo.gif)
```

> **Note**: GIFs can be large (10–50 MB for a 2-minute recording). Consider
> hosting on imgur or GitHub LFS, or use the MP4 option below.

---

## Option C — Convert to MP4

```bash
# Step 1: Generate GIF (see Option B)
agg demo/demo.cast demo/demo.gif --cols 120 --rows 35

# Step 2: Convert to MP4 with ffmpeg
ffmpeg -i demo/demo.gif \
    -vf "fps=15,scale=1440:-1:flags=lanczos" \
    -c:v libx264 -crf 22 -pix_fmt yuv420p \
    demo/demo.mp4
```

Upload to YouTube or Loom and link from `README.md`.

---

## Option D — Screen recorder (OBS / QuickTime)

If you prefer a full screen recording (with browser + terminal visible):

1. Start Streamlit: `bash demo/demo_commands.sh`
2. Open http://localhost:8501 in a browser
3. Start OBS (or QuickTime on macOS: File → New Screen Recording)
4. Walk through each Streamlit page (QC / DE / Pathways)
5. Export as MP4

### Suggested walkthrough script

| Time | Screen | Action |
|---|---|---|
| 0:00–0:20 | Terminal | Clone repo, install, generate data |
| 0:20–0:50 | Jupyter | Run demo notebook (accelerated) |
| 0:50–1:10 | Streamlit QC | Show QC metrics table |
| 1:10–1:50 | Streamlit DE | Interact with volcano plot (hover, zoom) |
| 1:50–2:10 | Streamlit Pathways | Show bubble chart, filter by padj |
| 2:10–2:20 | Terminal | Show final summary |

---

## Quick start (one command)

```bash
# Prerequisites: asciinema + agg installed
make demo-record   # records → demo/demo.cast, then converts to demo/demo.gif
```

The `Makefile` target handles both steps automatically.
