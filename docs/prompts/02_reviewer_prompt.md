Act as a strict architecture reviewer.

Review:
- CLAUDE.md
- docs/architecture.md
- docs/specs/*.md
- tasks/*.md
- docs/plan.md

Check for:
1. missing database models
2. missing API endpoints
3. Missing requirements.
4. places where the LLM controls critical logic
5. unclear OpenAI Agents SDK integration
6. missing audit logs
7. missing tests
8. missing mock mode
9. weak separation between deterministic workflow and LLM summary
10. unclear production hardening steps
11. Ambiguous requirements.
12. Over-engineering.
13. Scalability concerns.
14. Testing gaps.

Do not implement app code.

Revise the markdown specs and task files to fix issues.

Output:

- Critical Issues
- Recommended Changes
- Optional Improvements

Save to docs/review.md.

Do NOT implement code
