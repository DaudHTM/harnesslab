# Architecture

The control plane accepts curated task identifiers and validated harness configurations. It writes durable queued jobs to PostgreSQL (or SQLite for local development). Workers claim jobs with leases and run one agent per attempt. MCP tools operate against a per-attempt sandbox. The resulting patch is applied to a separate pristine checkout before hidden grading tests execute.

## Boundaries

- The model sees the issue, tool schemas, and tool outputs. It never receives the task's reference patch or hidden grading directory.
- Three MCP servers expose task context, repository operations, and execution. Names are prefixed (`repo__read_file`) to avoid collisions. The default transport runs three separate stdio processes through the official SDK. `mcp_transport: "in-process"` is also available. Tool processes receive a restricted environment and public task data with grading/reference paths removed.
- Docker workers create non-root, network-disabled containers with a read-only root filesystem and writable bounded tmpfs directories. Files are copied through tar over `docker exec`; the sandbox has no host mount or daemon socket. The worker necessarily accesses Docker, but the candidate code cannot.
- File tools reject absolute escapes, `.git` access, and outward symlinks. Shell execution is intentionally more powerful but remains inside the container. Local mode has no sandbox guarantee.
- The optional macOS backend runs commands, file operations, and Git patch collection through deny-by-default `sandbox-exec` policies. Candidate code cannot read the project/grading directories during agent execution, write outside its workspace/scratch directory, or connect to the model/API servers. This deprecated OS facility is a curated-task option with weaker resource limits than Docker.
- The grader uses the pinned base and a patch, not the agent's test outputs. Changes to tests and known test configuration paths are rejected. Hidden tests are supplied only to the separate grading environment.

## Leases and failure handling

Each running attempt has an owner, generation number, and expiring lease. Heartbeats atomically renew only the current owner/generation. After host sleep, that owner can renew an expired lease if nobody has reclaimed the job; a replacement changes the generation and fences the previous owner. Events and completion writes require a current lease. A replacement starts a clean second attempt. Two expired attempts terminate as an infrastructure error.

Queued cancellation is immediate. Running cancellation is checked during model/tool waits and subprocess polling. Mutating tool calls are not automatically retried; the resilient configuration retries only known read operations after timeouts. A replacement Docker attempt removes stale containers carrying its exact run label before starting a clean sandbox.

## Reproducibility and reporting

Task manifests pin commits. Configurations are hashed and versioned. Every event includes a run, attempt, monotonic sequence number, and wall-clock timestamp. Model events include cumulative token and estimated cost accounting. Reports aggregate the reservation ledger across attempts, retaining uncertain spend for interrupted calls. Older runs without ledger records fall back to their last usage snapshot per attempt.

The report separates infrastructure errors from valid trials, counts budget-exhausted attempts as unsuccessful valid trials, and shows a Wilson interval for trial success. Repeated trials are correlated by task; these intervals are descriptive and do not establish a significant difference between harnesses. Task-level paired analysis is still required for the final study.

## Known limitations

- Native macOS isolation and real PostgreSQL integration are verified locally. Docker execution still requires a Docker-enabled host; container command construction and scoped cleanup alone do not prove it.
- Experiment budgets use atomic reservations across workers, based on a conservative byte-based input estimate. Provider calls without usage responses retain their reservations and are shown separately as uncertain spend. Provider-specific token accounting can differ from estimates; reservations are safeguards, not billing guarantees.
- No exact model-call replay or exactly-once external effects. Trace playback is inspection of recorded events.
- Runs record harness commit/dirty status plus a source fingerprint, task-manifest hash, resolved Docker image ID, and verified managed-model identity. Studies lock the source fingerprint and reject runtime code drift. Externally managed model endpoints cannot be checksum verified by the harness alone.
- Full hidden-test anti-tampering requires stronger process separation if adversarial code is accepted. V1 accepts only curated tasks.
