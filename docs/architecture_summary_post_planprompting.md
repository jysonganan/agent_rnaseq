# Architecture Summary

## Pattern: Routing-Agent Design

A **LangGraph `StateGraph`** acts as the central router. The **Orchestrator Agent** (OpenAI Agents SDK) parses user intent into a validated `RunConfig` and dispatches to 10 **specialist sub-agents** — one per pipeline stage. Each sub-agent calls deterministic tools only; LLMs summarize results but never produce numbers.

## Pipeline Flow

```
FASTQ → QC (FastQC/RSeQC) → Alignment (STAR) → Quantification (HTSeq/Salmon/RSEM)
     → Variant Calling (GATK) → Splicing (rMATS) → DESeq2 → Reactome GSEA
     → Streamlit viz + UCSC tracks + HTML Report
```

## Key Architectural Decisions

| Decision | Rationale |
|---|---|
| LangGraph for routing | Durable checkpointed state — interrupted runs resume from last stage |
| R scripts as subprocesses | DESeq2/Reactome are R-native; called via `Rscript`, output validated in Python |
| Nextflow wraps heavy tools | Transparent local ↔ AWS Batch execution without changing Python code |
| Pydantic at every boundary | No unvalidated LLM text ever reaches DB writes or downstream tools |
| Separate Streamlit container | Read-only viz layer; cannot corrupt pipeline DB |

## 16 Implementation Tasks

Tasks are sequenced: scaffold → DB → tools (QC, align, quant, variant/splicing, DE/GSEA, scRNA) → agents (orchestrator, specialists) → FastAPI → Nextflow → AWS → Streamlit → integration tests → Docker. Each task has clear scope, acceptance criteria, and can be developed and tested independently.
