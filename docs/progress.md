# Implementation progress

## Implemented

- Strict, versioned task/config models and explicit paid-model pricing requirements.
- CLI for validation, runs, experiments, worker processing, comparison, export, cancellation, and API serving.
- Fresh-checkout grading and protected test/config patch paths.
- Three MCP servers through the official SDK and prefixed tool discovery.
- Separate stdio MCP processes with sanitized environments and an optional in-process transport.
- Atomic experiment-wide cost reservations, settlement, and uncertain-call accounting.
- Agent loop, structured tool results, per-task limits, context compaction, and read-only timeout retries.
- Fake fixture provider and two HTTP provider adapters.
- SQLite development store and PostgreSQL SQL adapter with leases and stale-worker fencing.
- Trace events, JSON export, comparison metrics, REST API, and SSE.
- React dashboard for experiment creation, comparison, traces, patches, and cancellation.
- An authored fixture, hidden grading tests, reference patch, and offline repository bootstrap.
- Thirty validated authored regression tasks across three licensed upstream repositories; frozen 10/20 development/held-out split.
- Free local Qwen3 inference with checksum-verified weights/runtime, no provider key, and loopback-only requests.
- Native macOS execution with tested file/network isolation; real models cannot use unsafe local mode.
- Harness/model/task provenance, immutable Docker image selection, and study source locks.
- Task-level paired reporting with separate configuration hashes and repeatability disclosure.
- Actual worker-process crash/replacement and bounded provider-rate-limit tests.
- Real PostgreSQL 17.11 integration: concurrent claims, atomic budgets, lease fencing, and worker/grading round trips.
- Three evidence-based failure case studies and a 180-second recorded terminal walkthrough (`docs/evidence/demo.cast`).
- Ten named fault scenarios with a reproducible CLI, JUnit artifacts, and an explicit infrastructure-only report.
- Dry-run/apply/watch orphan reconciliation scoped to known terminal jobs; unknown and active jobs are retained.
- MCP subprocess-crash and bounded-unresponsive-client lifecycle tests.
- Bounded MCP startup/discovery and nested error diagnostics; resumable SSE traces.
- Latest backend check: 58 passed, five Docker integration checks deferred until the private engine starts on AC power.

## Outstanding against the full project plan

- Enable the preserved GitHub Actions template after a GitHub credential with workflow permission is available. Source and evidence are uploaded to the private `DaudHTM/harnesslab` repository.
- Verify Docker execution and cleanup on a Docker-enabled host. Real PostgreSQL concurrency, budgets, fencing, and worker/grading round trips now pass against locally built PostgreSQL 17.11.
- Verify the implemented orphan reconciliation against real Docker containers after a worker is killed.
- Run the fresh free local-model pilot and 120-trial held-out evaluation on AC power; publish actual results and paired analysis. The earlier development pilot is published separately with negative results.
- Execute browser acceptance tests after browser access is granted. Case studies and the recorded terminal demo are available; visual UI verification remains incomplete.

These are completion requirements, not claims satisfied by the scripted demo.
