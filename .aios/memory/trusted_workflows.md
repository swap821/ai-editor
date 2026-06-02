# Trusted Workflows

_Patterns that succeeded >= 3x get promoted here._

- Per-phase commit on `master` after `pytest` is green (89 passing). Verified repeatedly across Phases 2-4g.
- Inject collaborators via FastAPI `Depends(...)` so tests override them with fakes (no Ollama / shell / network in tests).
