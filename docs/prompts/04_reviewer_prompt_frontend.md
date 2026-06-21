Act as a strict architecture reviewer.

Review:

CLAUDE.md
docs/architecture.md
docs/specs/*.md
tasks_frontend/*.md

Check for:

missing database models
missing API endpoints
Missing requirements.
places where the LLM controls critical logic
unclear OpenAI Agents SDK integration
missing audit logs
missing tests
missing mock mode
weak separation between deterministic workflow and LLM summary
unclear production hardening steps
Ambiguous requirements.
Over-engineering.
Scalability concerns.
Testing gaps.
Do not implement app code.

Revise the markdown specs and task files to fix issues.

Output:

Critical Issues
Recommended Changes
Optional Improvements
Save to docs/review_frontend.md.

Do NOT implement code


