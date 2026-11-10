# HarnessLab

An evaluation and debugging platform for coding-agent harnesses. Run a task at a pinned commit, inspect its MCP tool trace, grade the patch in a fresh environment, and compare harness configurations.

**Status:** working implementation with a validated 30-task authored regression corpus. The default model is an explicitly scripted integration fixture. A real Qwen3 local-model adapter is also available without API fees; the held-out comparison is still pending. Scripted fixture success is **not** evidence of AI coding ability.

## Quick start

Requires Python 3.12+, Git, and Node 20+ with pnpm. Docker is required for isolated task execution; a trusted-fixture-only local mode is available for development.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/bootstrap_demo.py
.venv/bin/harnesslab tasks validate benchmarks/tasks/tag-normalization.json --backend local --allow-unsafe-local
.venv/bin/harnesslab run benchmarks/tasks/tag-normalization.json --backend local --allow-unsafe-local
```

For the exact Python dependency versions verified during development, install `requirements-lock.txt` before the editable package.

Local mode runs code on your machine. Use it only for the included authored fixture. Docker is the default for every command; local execution always requires the explicit flag.

## Free local-model evaluations on Apple Silicon

The setup script downloads a pinned llama.cpp release and Qwen3-4B-Instruct-2507 Q8_0 weights, verifies both SHA-256 checksums, and keeps them inside `.harnesslab/local-model/`. The weights download is about 4.3 GB. No account or provider key is required.

```sh
.venv/bin/python scripts/local_model.py setup
.venv/bin/python scripts/local_model.py serve
```

In another terminal:

```sh
.venv/bin/harnesslab run benchmarks/tasks/tag-normalization.json --config-file configs/local-resilient.json --backend macos
```

The `macos` backend uses a deny-by-default native process policy: workspace writes only, approved runtime reads, and no networking. File operations and patch collection also run under the policy. It is for curated local evaluations and has weaker resource quotas than Docker. Real models are blocked from the unsafe `local` backend.

Model/runtime sources: [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md), [the selected GGUF model](https://huggingface.co/ggml-org/Qwen3-4B-Instruct-2507-Q8_0-GGUF).

## Rebuild and validate the corpus

```sh
.venv/bin/python scripts/build_corpus.py --fetch
.venv/bin/python scripts/validate_corpus.py --backend macos --workers 4
.venv/bin/python scripts/run_study.py pilot --backend macos
.venv/bin/python scripts/run_study.py held-out --backend macos
```

Use `--backend docker` on a Docker-enabled host. The 30 tasks are deliberately introduced regressions, split into 10 development and 20 held-out tasks. They are not historical upstream issues or a contamination-resistant benchmark. Each includes hidden checks, upstream regression tests, attribution, and a reference patch.

The study runner freezes the harness source hash, checkpoints completed runs, and supports `--resume EXPERIMENT_ID`. The held-out matrix contains 120 trials: 20 tasks × 2 configurations × 3 repetitions. Fixed-seed repetitions measure repeatability rather than independent stochastic samples.

Held-out studies wait for external power on macOS and check power again between trials. To run the remaining pilot and then the full comparison on power, use `scripts/run_study.py pilot --backend macos --wait-for-power --then-held-out`. Completed phases publish raw traces, paired reports, and checksum-verified source archives. Interactive workers do not claim controlled study jobs.

### Dashboard

In separate terminals:

```sh
.venv/bin/harnesslab serve
```

```sh
.venv/bin/harnesslab worker --backend local --allow-unsafe-local
```

```sh
cd frontend
pnpm install
pnpm dev
```

Open [the dashboard](http://localhost:5173), create a demo experiment, and inspect its completed runs. The dashboard includes comparisons, live trace events, patches, grading logs, cancellation, and JSON export.

### Isolated execution

```sh
docker build -f docker/task.Dockerfile -t harnesslab-task:local .
.venv/bin/harnesslab tasks validate benchmarks/tasks/tag-normalization.json
.venv/bin/harnesslab run benchmarks/tasks/tag-normalization.json
```

Task containers run as a non-root user with no network, no host mounts, a read-only root filesystem, bounded tmpfs storage, and resource limits. This is designed for curated tasks, not a public hostile-code execution service.

`docker compose up --build` starts PostgreSQL, bootstraps the fixture, serves the built dashboard on port 8000, and starts a worker. Build the task image first using the command above. The Compose worker accesses the host Docker socket to create child containers; child containers never receive that socket. Compose execution is not yet verified on this host.

On Apple Silicon, an optional free engine uses project-local Lima, Docker CLI, and Compose downloads with verified checksums. It creates a private VM with no home-directory mounts and leaves global Docker contexts alone:

```sh
.venv/bin/python scripts/local_containers.py setup
.venv/bin/python scripts/local_containers.py start --wait-for-power --verify
.venv/bin/python scripts/verify_compose.py --private-engine
.venv/bin/python scripts/local_containers.py stop
```

The verification command builds the task image and runs the five real Docker integration checks. The Compose check exercises the API, worker, MCP tools, fresh grading, trace schema, patch retrieval, and static bundle delivery; it does not verify browser rendering. To use this engine from another terminal, load the exports printed by `scripts/local_containers.py env`.

### Experiments and injected failures

```sh
.venv/bin/harnesslab experiment configs/demo-experiment.json
.venv/bin/harnesslab worker --backend local --allow-unsafe-local --once
.venv/bin/harnesslab compare EXPERIMENT_ID
.venv/bin/harnesslab export EXPERIMENT_ID results.json
.venv/bin/harnesslab run benchmarks/tasks/tag-normalization.json --config resilient --fault mcp_timeout --backend local --allow-unsafe-local
```

`--once` drains currently claimable interactive jobs and exits. Direct agent-run injection supports `mcp_timeout` and `malformed_output`; the named scenario suite covers process crashes, provider failures, hanging commands, budgets, and cancellation. Experiments default to a $5 shared budget; set `budget_usd` in the experiment spec to change it. Per-task budgets also apply. Interrupted provider calls retain their reservations as uncertain spend.

Run the named infrastructure scenarios with `.venv/bin/python scripts/fault_scenarios.py all`, or replace `all` with `worker_crash`, `provider_rate_limit`, `mcp_crash`, `mcp_unresponsive`, `live_cancellation`, `hanging_command`, `budget_exhaustion`, `path_injection`, `mcp_timeout`, or `malformed_output`. The checked-in [scenario report](docs/evidence/fault-matrix/summary.json) records ten passing checks. These deterministic scenarios test runtime boundaries and do not measure a learned model's recovery rate.

### Orphan-container maintenance

`scripts/reconcile.py` lists managed containers and marks only containers belonging to known terminal jobs as eligible for cleanup. It retains unknown jobs, active jobs, and containers without valid HarnessLab labels. The default is a dry run; `--apply` deletes eligible containers and `--watch --apply` repeats the maintenance pass. This logic has unit coverage; live Docker cleanup remains unverified on this host.

### Real models

Set `HARNESSLAB_MODEL_API_KEY` for an OpenAI-compatible chat-completions endpoint, with optional `HARNESSLAB_MODEL_BASE_URL`. Set `HARNESSLAB_ANTHROPIC_API_KEY` for Anthropic. Keys stay in the trusted worker; they are not copied to task containers or included in traces.

Create a JSON config matching `HarnessConfig` with `provider`, `model`, positive `input_usd_per_million`, positive `output_usd_per_million`, and `pricing_date`, then pass `--config-file PATH`. Select a model that supports tool calls. Pricing is supplied explicitly rather than guessed. Do not use fake-model results as a baseline for model performance.

## Tests

```sh
.venv/bin/python -m pytest -q
cd frontend
pnpm build
```

Tests use no paid APIs. They cover independent grading, real MCP calls, lease fencing, a worker process crash/replacement, concurrent claims, cancellation, path escapes, deadlines, rate limits, tool faults, and API behavior. macOS-specific tests verify file/network boundaries. Browser tests exist but have not been executed because browser access was declined.

## Persistence

The default SQLite database at `.harnesslab/state.db` supports development without services. Set `HARNESSLAB_DATABASE_URL=postgresql://...` for PostgreSQL with `FOR UPDATE SKIP LOCKED` claims. Workers share the database and artifact directory. Real PostgreSQL concurrency, budget/fencing, and worker/grading tests pass against PostgreSQL 17.11; their JUnit report is in `docs/evidence/postgres.xml`.

For a free, private local PostgreSQL test instance, `scripts/local_postgres.py setup` builds the pinned official source inside the workspace and `scripts/local_postgres.py start` starts a Unix-socket-only server. It does not modify a system installation. The start command prints the test connection URL; set `HARNESSLAB_TEST_POSTGRES_URL` to run `tests/test_postgres.py`.

See [architecture](docs/architecture.md), [implementation progress](docs/progress.md), and [benchmark protocol](docs/benchmark.md).

The [failure case studies](docs/case-studies.md) link raw evidence. A three-minute [terminal recording](docs/evidence/demo.cast) captures real CLI runs and replays the labeled real-model case evidence. It includes reading pauses and can be played with an asciinema-compatible player. Browser verification is separate and remains unverified.
