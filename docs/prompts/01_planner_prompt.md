You are the architect/planner for this repo.

Goal:
Build a production-style computational pipeline agent for RNA-seq analysis.
The bioinformatics workflow can handle both single-cell and bulk RNA-seq analysis in local or in AWS s3 with AWS Batch jobs set-up. It's an end-to-end standard RNA-Seq analysis workflow starting from the FASTQ file to the differential gene expression analysis, VCF call, splicing analysis, gene set enrichment analysis and visualization of differential gene analysis (as report and visualization app) and genome browser visualization. 

It handles different Genome (Genome FASTA). It also can do both alignment to genome and transcriptome. 

Include a small example of single-cell RNA-Seq analysis in the folder of this repo or database.

Runtime stack:
- FastQC
- STAR
- Salmon
- HTSeq
- CellRanger
- samtools
- RSeQC for post-alignment QC
- GATK for variant caller
- RSEM
- DESeq2
- UCSC browser
- Reactome for pathway enrichment analysis
- streamlit app for the DESeq2, pathway analysis, QC visualization
- nextflow
- pytest
- Docker and docker-compose
- AWS S3
- AWS Batch
- FastAPI
- OpenAI Agents SDK as the agent runtime
- LangGraph for the durable and structured states, memory and routing
- SQLite for local dev
- PostgreSQL-ready design
- SQLAlchemy ORM
- Pydantic schemas

Safety constraints:
- Critical calculations must be deterministic Python code (and R code for the R packages), not controlled by the LLM
- LLM may summarize validated results only and decide the tool or parameters for the user's need or data inputs.

Do not implement application code yet.

Generate an implementation plan. Adopt the routing agents design for optimized agent performance and context engineering.

Include:

1. High-level architecture.
2. Major components.
3. Database schema.
4. API design.
5. Tool interfaces.
6. Task breakdown.
7. Risks and assumptions.
8. Testing strategy.

Generate implementation tasks under tasks/.

Each task should:

- have clear scope,
- contain acceptance criteria,
- be independently testable,
- modify as few components as possible.
- Goal
- Requirements
- Files to create/edit
- Acceptance criteria
- Definition of Done


Create:

1. CLAUDE.md
2. docs/architecture.md
3. docs/specs/data_models.md
4. docs/specs/api_contracts.md
5. docs/specs/tool_contracts.md
6. docs/specs/safety_policy.md

After creating the markdown files, stop and summarize the proposed architecture.
Do not write app code yet.
