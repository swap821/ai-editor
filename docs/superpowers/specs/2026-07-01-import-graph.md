# Fusion K1 Import Graph and Dependency Triage

Date: 2026-07-01

This document records the K1 supply-chain triage and a live AST-derived import graph for `aios/`. It is evidence for cleanup decisions, not deletion authority by itself: dynamic imports and external entrypoints still need human review before removing a module.

## Dependency Triage

| Dependency | Import evidence | Metadata evidence | Decision |
| --- | --- | --- | --- |
| `httpx2==2.3.0` | No `aios/` or `tests/` import of `httpx2`. | Requires `httpcore2==2.3.0` and `truststore>=0.10`; `pip show` reports no `Required-by` in this environment. Project URL is `pydantic/httpx2`, so provenance exists, but the shadow-client naming is dependency-smell shaped. | Removed from `requirements.txt`; standard `httpx==0.28.1` remains for HuggingFace/FastAPI-compatible HTTP needs. |
| `httpcore2==2.3.0` | No `aios/` or `tests/` import of `httpcore2`. | Only required by `httpx2` locally; `httpx==0.28.1` already uses `httpcore==1.0.9`. | Removed with `httpx2`. |
| `truststore==0.10.4` | No `aios/` or `tests/` import of `truststore`. | Only required by `httpx2`/`httpcore2` locally. | Removed with the unused `httpx2` chain. |
| `hf-xet==1.5.0` | No direct product import. | `huggingface-hub==1.17.0` conditionally requires `hf-xet>=1.4.3,<2.0.0` on x86_64/amd64/arm64/aarch64. | Kept; it is a HuggingFace transfer backend dependency on this platform class. |
| `sympy==1.14.0` | No direct product import. | `torch` requires `sympy>=1.13.3`. | Kept; do not disturb ML stack pins in K1. |
| `shellingham==1.5.4` | No direct product import. | `typer` requires `shellingham>=1.3.0`. | Kept as Typer transitive support. |
| `mando==0.7.1` | No direct product import. | `radon` requires `mando>=0.6,<0.8`. | Kept as Radon support for self-analysis metrics. |
| `rank-bm25==0.2.2` | `aios/memory/retrieval.py` imports `rank_bm25.BM25Okapi`. | No local package requires it, but the product imports it directly. | Kept. |
| `annotated-doc==0.0.4` | No direct product import. | `fastapi` and `typer` require `annotated-doc>=0.0.2`. | Kept as FastAPI/Typer transitive support. |

## Import Graph Method

- Source: every `*.py` file under `aios/` at K1 time.
- Parser: Python `ast`, resolving both `import aios.x` and `from aios.x import y` when `y` is an internal submodule.
- Status meanings: `live` has an internal importer; `live root` is an external entrypoint; `live package marker` is an `__init__.py` package marker; `orphan candidate` has no internal importer in this static graph and needs separate review before deletion.

## Internal Import Edges

| Module | Internal imports | Imported by | Status |
| --- | --- | --- | --- |
| `aios` | none | `aios.__main__`<br>`aios.agents.reflection_agent`<br>`aios.agents.rollback_engine`<br>`aios.agents.self_analysis_agent`<br>`aios.agents.swarm`<br>`aios.agents.swarm_patterns`<br>`aios.agents.tool_agent`<br>`aios.agents.tool_handlers`<br>`aios.api.main`<br>`aios.core.approvals`<br>`aios.core.autonomy`<br>`aios.core.bedrock`<br>`aios.core.confidence_filter`<br>`aios.core.executor`<br>`aios.core.gemini`<br>`aios.core.llm`<br>`aios.core.planner`<br>`aios.core.router_wiring`<br>`aios.core.self_apply`<br>`aios.core.verification_strength`<br>`aios.council.council_orchestrator`<br>`aios.council.council_state`<br>`aios.council.queens.memory`<br>`aios.council.queens.planner`<br>`aios.memory.alignment_evaluation`<br>`aios.memory.compaction`<br>`aios.memory.consolidation`<br>`aios.memory.conversation`<br>`aios.memory.curriculum`<br>`aios.memory.db`<br>`aios.memory.development`<br>`aios.memory.embeddings`<br>`aios.memory.episodic`<br>`aios.memory.facts`<br>`aios.memory.mistake`<br>`aios.memory.retrieval`<br>`aios.memory.semantic`<br>`aios.memory.skills`<br>`aios.runtime.concurrency`<br>`aios.runtime.intelligence_gateway`<br>`aios.runtime.worker_api`<br>`aios.runtime.worker_entry`<br>`aios.security.audit_logger`<br>`aios.security.gateway`<br>`aios.security.injection_shield`<br>`aios.security.scope_lock` | live package marker |
| `aios.__main__` | `aios`<br>`aios.config` | none | live root (entrypoint: python -m aios) |
| `aios.agents` | none | `aios.agents.tool_agent`<br>`aios.agents.tool_handlers` | live package marker |
| `aios.agents.reflection_agent` | `aios`<br>`aios.config`<br>`aios.core.llm`<br>`aios.core.verification_strength`<br>`aios.memory.mistake` | `aios.api.main` | live |
| `aios.agents.role_pass` | `aios.agents.tool_agent` | `aios.api.main` | live |
| `aios.agents.rollback_engine` | `aios`<br>`aios.config` | `aios.api.main`<br>`aios.runtime.snapshots` | live |
| `aios.agents.self_analysis_agent` | `aios`<br>`aios.config`<br>`aios.core.llm`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.agents.tool_handlers`<br>`aios.core.self_apply` | live |
| `aios.agents.swarm` | `aios`<br>`aios.agents.swarm_patterns`<br>`aios.agents.tool_agent`<br>`aios.config` | `aios.api.main` | live |
| `aios.agents.swarm_patterns` | `aios`<br>`aios.config`<br>`aios.core.verification_strength`<br>`aios.memory.db`<br>`aios.memory.relevance` | `aios.agents.swarm`<br>`aios.api.main` | live |
| `aios.agents.tool_agent` | `aios`<br>`aios.agents`<br>`aios.agents.tool_handlers`<br>`aios.agents.tool_loop_helpers`<br>`aios.config`<br>`aios.core.autonomy`<br>`aios.core.executor`<br>`aios.core.llm`<br>`aios.core.planner`<br>`aios.core.verification_strength`<br>`aios.core.verifier`<br>`aios.security.audit_logger`<br>`aios.security.gateway` | `aios.agents.role_pass`<br>`aios.agents.swarm`<br>`aios.api.main` | live |
| `aios.agents.tool_handlers` | `aios`<br>`aios.agents`<br>`aios.agents.self_analysis_agent`<br>`aios.agents.tool_loop_helpers`<br>`aios.config`<br>`aios.core.planner`<br>`aios.core.verifier`<br>`aios.security`<br>`aios.security.gateway`<br>`aios.security.scope_lock`<br>`aios.security.secret_scanner` | `aios.agents.tool_agent` | live |
| `aios.agents.tool_loop_helpers` | `aios.core.verification_strength`<br>`aios.core.verifier` | `aios.agents.tool_agent`<br>`aios.agents.tool_handlers` | live |
| `aios.api` | none | none | live package marker |
| `aios.api.main` | `aios`<br>`aios.agents.reflection_agent`<br>`aios.agents.role_pass`<br>`aios.agents.rollback_engine`<br>`aios.agents.swarm`<br>`aios.agents.swarm_patterns`<br>`aios.agents.tool_agent`<br>`aios.config`<br>`aios.core`<br>`aios.core.alignment`<br>`aios.core.approvals`<br>`aios.core.autonomy`<br>`aios.core.bedrock`<br>`aios.core.catalog`<br>`aios.core.events`<br>`aios.core.executor`<br>`aios.core.gemini`<br>`aios.core.llm`<br>`aios.core.metrics`<br>`aios.core.model_selector`<br>`aios.core.planner`<br>`aios.core.router`<br>`aios.core.router_wiring`<br>`aios.core.self_apply`<br>`aios.core.session_manager`<br>`aios.core.verification_strength`<br>`aios.core.verifier`<br>`aios.core.websearch`<br>`aios.council`<br>`aios.council.council_state`<br>`aios.council.queen_verdict`<br>`aios.logging_config`<br>`aios.memory.alignment_evaluation`<br>`aios.memory.compaction`<br>`aios.memory.consolidation`<br>`aios.memory.conversation`<br>`aios.memory.crag`<br>`aios.memory.curriculum`<br>`aios.memory.db`<br>`aios.memory.development`<br>`aios.memory.embeddings`<br>`aios.memory.episodic`<br>`aios.memory.facts`<br>`aios.memory.mistake`<br>`aios.memory.retrieval`<br>`aios.memory.self_model`<br>`aios.memory.semantic`<br>`aios.memory.skills`<br>`aios.memory.working`<br>`aios.runtime.contracts`<br>`aios.runtime.king_report`<br>`aios.runtime.run_ledger`<br>`aios.runtime.snapshots`<br>`aios.security.audit_logger`<br>`aios.security.gateway`<br>`aios.security.injection_shield`<br>`aios.security.secret_scanner` | none | live root (entrypoint: FastAPI/uvicorn app) |
| `aios.config` | none | `aios.__main__`<br>`aios.agents.reflection_agent`<br>`aios.agents.rollback_engine`<br>`aios.agents.self_analysis_agent`<br>`aios.agents.swarm`<br>`aios.agents.swarm_patterns`<br>`aios.agents.tool_agent`<br>`aios.agents.tool_handlers`<br>`aios.api.main`<br>`aios.core.approvals`<br>`aios.core.autonomy`<br>`aios.core.bedrock`<br>`aios.core.confidence_filter`<br>`aios.core.executor`<br>`aios.core.gemini`<br>`aios.core.llm`<br>`aios.core.planner`<br>`aios.core.router_wiring`<br>`aios.core.self_apply`<br>`aios.core.verification_strength`<br>`aios.council.council_orchestrator`<br>`aios.council.council_state`<br>`aios.council.queens.memory`<br>`aios.council.queens.planner`<br>`aios.memory.alignment_evaluation`<br>`aios.memory.compaction`<br>`aios.memory.consolidation`<br>`aios.memory.conversation`<br>`aios.memory.curriculum`<br>`aios.memory.db`<br>`aios.memory.development`<br>`aios.memory.embeddings`<br>`aios.memory.episodic`<br>`aios.memory.facts`<br>`aios.memory.mistake`<br>`aios.memory.retrieval`<br>`aios.memory.semantic`<br>`aios.memory.skills`<br>`aios.probe_common`<br>`aios.runtime.concurrency`<br>`aios.runtime.intelligence_gateway`<br>`aios.runtime.worker_api`<br>`aios.runtime.worker_entry`<br>`aios.security.audit_logger`<br>`aios.security.gateway`<br>`aios.security.injection_shield`<br>`aios.security.scope_lock` | live |
| `aios.core` | none | `aios.api.main`<br>`aios.core.router_wiring` | live package marker |
| `aios.core.alignment` | `aios.core.llm`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.core.approvals` | `aios`<br>`aios.config`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.core.autonomy` | `aios`<br>`aios.config`<br>`aios.core.verification_strength`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.agents.tool_agent`<br>`aios.api.main` | live |
| `aios.core.bedrock` | `aios`<br>`aios.config`<br>`aios.core.llm`<br>`aios.core.privacy_filter` | `aios.api.main` | live |
| `aios.core.catalog` | none | `aios.api.main`<br>`aios.core.router_wiring` | live |
| `aios.core.confidence_filter` | `aios`<br>`aios.config` | `aios.core.planner` | live |
| `aios.core.events` | none | `aios.api.main` | live |
| `aios.core.executor` | `aios`<br>`aios.config`<br>`aios.security.audit_logger`<br>`aios.security.gateway` | `aios.agents.tool_agent`<br>`aios.api.main`<br>`aios.core.self_apply`<br>`aios.core.verifier`<br>`aios.runtime.worker_api` | live |
| `aios.core.failover` | `aios.core.llm`<br>`aios.core.privacy_filter` | `aios.core.router_wiring` | live |
| `aios.core.gemini` | `aios`<br>`aios.config`<br>`aios.core.llm`<br>`aios.core.privacy_filter` | `aios.api.main` | live |
| `aios.core.llm` | `aios`<br>`aios.config` | `aios.agents.reflection_agent`<br>`aios.agents.self_analysis_agent`<br>`aios.agents.tool_agent`<br>`aios.api.main`<br>`aios.core.alignment`<br>`aios.core.bedrock`<br>`aios.core.failover`<br>`aios.core.gemini`<br>`aios.core.planner`<br>`aios.council.queens.planner`<br>`aios.council.reasoning`<br>`aios.runtime.intelligence_gateway` | live |
| `aios.core.metrics` | `aios.security.audit_logger` | `aios.api.main` | live |
| `aios.core.model_selector` | none | `aios.api.main`<br>`aios.core.router`<br>`aios.core.router_wiring` | live |
| `aios.core.planner` | `aios`<br>`aios.config`<br>`aios.core.confidence_filter`<br>`aios.core.llm`<br>`aios.memory.development`<br>`aios.memory.mistake`<br>`aios.memory.skills` | `aios.agents.tool_agent`<br>`aios.agents.tool_handlers`<br>`aios.api.main` | live |
| `aios.core.privacy_filter` | none | `aios.core.bedrock`<br>`aios.core.failover`<br>`aios.core.gemini` | live |
| `aios.core.router` | `aios.core.model_selector` | `aios.api.main`<br>`aios.core.router_wiring` | live |
| `aios.core.router_wiring` | `aios`<br>`aios.config`<br>`aios.core`<br>`aios.core.catalog`<br>`aios.core.failover`<br>`aios.core.model_selector`<br>`aios.core.router`<br>`aios.logging_config` | `aios.api.main` | live |
| `aios.core.self_apply` | `aios`<br>`aios.agents.self_analysis_agent`<br>`aios.config`<br>`aios.core.executor`<br>`aios.core.verifier`<br>`aios.memory.db`<br>`aios.security.audit_logger`<br>`aios.security.gateway`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.core.session_manager` | none | `aios.api.main` | live |
| `aios.core.verification_strength` | `aios`<br>`aios.config` | `aios.agents.reflection_agent`<br>`aios.agents.swarm_patterns`<br>`aios.agents.tool_agent`<br>`aios.agents.tool_loop_helpers`<br>`aios.api.main`<br>`aios.core.autonomy`<br>`aios.core.verifier`<br>`aios.council.queens.critique`<br>`aios.council.queens.testing`<br>`aios.memory.curriculum`<br>`aios.memory.mistake`<br>`aios.memory.skills`<br>`aios.runtime.king_report`<br>`aios.runtime.run_ledger` | live |
| `aios.core.verifier` | `aios.core.executor`<br>`aios.core.verification_strength` | `aios.agents.tool_agent`<br>`aios.agents.tool_handlers`<br>`aios.agents.tool_loop_helpers`<br>`aios.api.main`<br>`aios.core.self_apply`<br>`aios.council.queens.testing` | live |
| `aios.core.websearch` | `aios.logging_config`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.council` | `aios.council.council_orchestrator`<br>`aios.council.queens` | `aios.api.main` | live package marker |
| `aios.council.council_orchestrator` | `aios`<br>`aios.config`<br>`aios.council.council_state`<br>`aios.council.king_reasoning`<br>`aios.council.queen_verdict`<br>`aios.council.queens.critique`<br>`aios.council.queens.memory`<br>`aios.council.queens.planner`<br>`aios.council.queens.security`<br>`aios.council.queens.testing`<br>`aios.runtime.contracts`<br>`aios.runtime.king_report`<br>`aios.runtime.run_ledger`<br>`aios.runtime.spawner` | `aios.council` | live |
| `aios.council.council_state` | `aios`<br>`aios.config`<br>`aios.runtime.contracts` | `aios.api.main`<br>`aios.council.council_orchestrator` | live |
| `aios.council.king_reasoning` | `aios.runtime.contracts` | `aios.council.council_orchestrator` | live |
| `aios.council.queen_verdict` | `aios.runtime.contracts` | `aios.api.main`<br>`aios.council.council_orchestrator`<br>`aios.council.queens.security` | live |
| `aios.council.queens` | `aios.council.queens.critique`<br>`aios.council.queens.memory`<br>`aios.council.queens.planner`<br>`aios.council.queens.security`<br>`aios.council.queens.testing` | `aios.council` | live package marker |
| `aios.council.queens.critique` | `aios.core.verification_strength`<br>`aios.runtime.contracts` | `aios.council.council_orchestrator`<br>`aios.council.queens` | live |
| `aios.council.queens.memory` | `aios`<br>`aios.config`<br>`aios.council.reasoning`<br>`aios.runtime.contracts` | `aios.council.council_orchestrator`<br>`aios.council.queens` | live |
| `aios.council.queens.planner` | `aios`<br>`aios.config`<br>`aios.core.llm`<br>`aios.council.reasoning`<br>`aios.runtime.contracts` | `aios.council.council_orchestrator`<br>`aios.council.queens` | live |
| `aios.council.queens.security` | `aios.council.queen_verdict`<br>`aios.runtime.contracts`<br>`aios.security.gateway` | `aios.council.council_orchestrator`<br>`aios.council.queens` | live |
| `aios.council.queens.testing` | `aios.core.verification_strength`<br>`aios.core.verifier`<br>`aios.runtime.contracts` | `aios.council.council_orchestrator`<br>`aios.council.queens` | live |
| `aios.council.reasoning` | `aios.core.llm`<br>`aios.memory.mistake`<br>`aios.runtime.contracts` | `aios.council.queens.memory`<br>`aios.council.queens.planner` | live |
| `aios.council.service_definitions` | `aios.runtime.contracts` | none | orphan candidate: no internal importer found |
| `aios.logging_config` | none | `aios.api.main`<br>`aios.core.router_wiring`<br>`aios.core.websearch`<br>`aios.memory.compaction` | live |
| `aios.memory` | none | none | live package marker |
| `aios.memory.alignment_evaluation` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.memory.compaction` | `aios`<br>`aios.config`<br>`aios.logging_config`<br>`aios.memory.db`<br>`aios.memory.embeddings`<br>`aios.memory.episodic`<br>`aios.memory.semantic`<br>`aios.memory.working`<br>`aios.security.audit_logger`<br>`aios.security.gateway` | `aios.api.main` | live |
| `aios.memory.consolidation` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.memory.facts`<br>`aios.memory.mistake`<br>`aios.memory.semantic` | `aios.api.main` | live |
| `aios.memory.conversation` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.memory.crag` | `aios.memory.relevance` | `aios.api.main` | live |
| `aios.memory.curriculum` | `aios`<br>`aios.config`<br>`aios.core.verification_strength`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.api.main` | live |
| `aios.memory.db` | `aios`<br>`aios.config`<br>`aios.memory.relevance` | `aios.agents.self_analysis_agent`<br>`aios.agents.swarm_patterns`<br>`aios.api.main`<br>`aios.core.autonomy`<br>`aios.core.self_apply`<br>`aios.memory.alignment_evaluation`<br>`aios.memory.compaction`<br>`aios.memory.consolidation`<br>`aios.memory.conversation`<br>`aios.memory.curriculum`<br>`aios.memory.development`<br>`aios.memory.episodic`<br>`aios.memory.facts`<br>`aios.memory.mistake`<br>`aios.memory.retrieval`<br>`aios.memory.semantic`<br>`aios.memory.skills` | live |
| `aios.memory.development` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.memory.relevance`<br>`aios.security.secret_scanner` | `aios.api.main`<br>`aios.core.planner` | live |
| `aios.memory.embeddings` | `aios`<br>`aios.config` | `aios.api.main`<br>`aios.memory.compaction`<br>`aios.memory.retrieval`<br>`aios.memory.semantic`<br>`aios.security.injection_shield` | live |
| `aios.memory.episodic` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.api.main`<br>`aios.memory.compaction` | live |
| `aios.memory.facts` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.security.secret_scanner` | `aios.api.main`<br>`aios.memory.consolidation` | live |
| `aios.memory.mistake` | `aios`<br>`aios.config`<br>`aios.core.verification_strength`<br>`aios.memory.db`<br>`aios.memory.relevance`<br>`aios.security.secret_scanner` | `aios.agents.reflection_agent`<br>`aios.api.main`<br>`aios.core.planner`<br>`aios.council.reasoning`<br>`aios.memory.consolidation` | live |
| `aios.memory.relevance` | none | `aios.agents.swarm_patterns`<br>`aios.memory.crag`<br>`aios.memory.db`<br>`aios.memory.development`<br>`aios.memory.mistake`<br>`aios.memory.semantic`<br>`aios.memory.skills` | live |
| `aios.memory.retrieval` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.memory.embeddings` | `aios.api.main` | live |
| `aios.memory.self_model` | none | `aios.api.main` | live |
| `aios.memory.semantic` | `aios`<br>`aios.config`<br>`aios.memory.db`<br>`aios.memory.embeddings`<br>`aios.memory.relevance`<br>`aios.security.secret_scanner` | `aios.api.main`<br>`aios.memory.compaction`<br>`aios.memory.consolidation` | live |
| `aios.memory.skills` | `aios`<br>`aios.config`<br>`aios.core.verification_strength`<br>`aios.memory.db`<br>`aios.memory.relevance`<br>`aios.security.secret_scanner` | `aios.api.main`<br>`aios.core.planner` | live |
| `aios.memory.working` | none | `aios.api.main`<br>`aios.memory.compaction` | live |
| `aios.probe_common` | `aios.config` | none | live root (entrypoint: probe helpers) |
| `aios.runtime` | none | none | live package marker |
| `aios.runtime.backends` | `aios.runtime.contracts`<br>`aios.runtime.secret_policy` | `aios.runtime.run_ledger`<br>`aios.runtime.spawner` | live |
| `aios.runtime.budget_guard` | `aios.runtime.contracts` | `aios.runtime.intelligence_gateway` | live |
| `aios.runtime.concurrency` | `aios`<br>`aios.config` | `aios.runtime.spawner` | live |
| `aios.runtime.contracts` | none | `aios.api.main`<br>`aios.council.council_orchestrator`<br>`aios.council.council_state`<br>`aios.council.king_reasoning`<br>`aios.council.queen_verdict`<br>`aios.council.queens.critique`<br>`aios.council.queens.memory`<br>`aios.council.queens.planner`<br>`aios.council.queens.security`<br>`aios.council.queens.testing`<br>`aios.council.reasoning`<br>`aios.council.service_definitions`<br>`aios.runtime.backends`<br>`aios.runtime.budget_guard`<br>`aios.runtime.intelligence_gateway`<br>`aios.runtime.king_report`<br>`aios.runtime.run_ledger`<br>`aios.runtime.snapshots`<br>`aios.runtime.spawner`<br>`aios.runtime.worker_api`<br>`aios.runtime.worker_entry` | live |
| `aios.runtime.intelligence_gateway` | `aios`<br>`aios.config`<br>`aios.core.llm`<br>`aios.runtime.budget_guard`<br>`aios.runtime.contracts`<br>`aios.runtime.secret_policy` | `aios.runtime.worker_api`<br>`aios.runtime.worker_entry` | live |
| `aios.runtime.king_report` | `aios.core.verification_strength`<br>`aios.runtime.contracts` | `aios.api.main`<br>`aios.council.council_orchestrator`<br>`aios.runtime.spawner` | live |
| `aios.runtime.run_ledger` | `aios.core.verification_strength`<br>`aios.runtime.backends`<br>`aios.runtime.contracts` | `aios.api.main`<br>`aios.council.council_orchestrator`<br>`aios.runtime.spawner` | live |
| `aios.runtime.secret_policy` | `aios.security.secret_scanner` | `aios.runtime.backends`<br>`aios.runtime.intelligence_gateway`<br>`aios.runtime.worker_api` | live |
| `aios.runtime.snapshots` | `aios.agents.rollback_engine`<br>`aios.runtime.contracts` | `aios.api.main`<br>`aios.runtime.spawner` | live |
| `aios.runtime.spawner` | `aios.runtime.backends`<br>`aios.runtime.concurrency`<br>`aios.runtime.contracts`<br>`aios.runtime.king_report`<br>`aios.runtime.run_ledger`<br>`aios.runtime.snapshots` | `aios.council.council_orchestrator` | live |
| `aios.runtime.worker_api` | `aios`<br>`aios.config`<br>`aios.core.executor`<br>`aios.runtime.contracts`<br>`aios.runtime.intelligence_gateway`<br>`aios.runtime.secret_policy` | `aios.runtime.worker_entry` | live |
| `aios.runtime.worker_entry` | `aios`<br>`aios.config`<br>`aios.runtime.contracts`<br>`aios.runtime.intelligence_gateway`<br>`aios.runtime.worker_api` | none | live root (entrypoint: Council worker subprocess) |
| `aios.security` | none | `aios.agents.tool_handlers` | live package marker |
| `aios.security.audit_logger` | `aios`<br>`aios.config`<br>`aios.security.gateway`<br>`aios.security.secret_scanner` | `aios.agents.tool_agent`<br>`aios.api.main`<br>`aios.core.executor`<br>`aios.core.metrics`<br>`aios.core.self_apply`<br>`aios.memory.compaction` | live |
| `aios.security.gateway` | `aios`<br>`aios.config`<br>`aios.security.scope_lock`<br>`aios.security.secret_scanner` | `aios.agents.tool_agent`<br>`aios.agents.tool_handlers`<br>`aios.api.main`<br>`aios.core.executor`<br>`aios.core.self_apply`<br>`aios.council.queens.security`<br>`aios.memory.compaction`<br>`aios.security.audit_logger` | live |
| `aios.security.injection_shield` | `aios`<br>`aios.config`<br>`aios.memory.embeddings` | `aios.api.main` | live |
| `aios.security.scope_lock` | `aios`<br>`aios.config` | `aios.agents.tool_handlers`<br>`aios.security.gateway` | live |
| `aios.security.secret_scanner` | none | `aios.agents.self_analysis_agent`<br>`aios.agents.tool_handlers`<br>`aios.api.main`<br>`aios.core.alignment`<br>`aios.core.approvals`<br>`aios.core.autonomy`<br>`aios.core.self_apply`<br>`aios.core.websearch`<br>`aios.memory.alignment_evaluation`<br>`aios.memory.conversation`<br>`aios.memory.curriculum`<br>`aios.memory.development`<br>`aios.memory.episodic`<br>`aios.memory.facts`<br>`aios.memory.mistake`<br>`aios.memory.semantic`<br>`aios.memory.skills`<br>`aios.runtime.secret_policy`<br>`aios.security.audit_logger`<br>`aios.security.gateway` | live |

## Orphan Candidates

- `aios.council.service_definitions`: no internal importer in the AST graph. Do not delete solely from this result; verify external entrypoints, docs, and tests first.
