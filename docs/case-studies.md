# Failure case studies

## 1. The model described a fix without writing it

The real local Qwen3 baseline run `ff2fe51ccc4444ccaa295358b1d0e021` inspected the normalization implementation and tests, described a correct replacement in chat, ran the existing visible test, and claimed completion. Its recorded patch was empty. Independent grading failed three hidden checks for trimming, deduplication, and empty inputs. The [baseline trace](evidence/empty-patch-baseline.json) and [feedback trace](evidence/empty-patch-feedback.json) retain the evidence.

The resilient harness now checks the actual Git diff before accepting a final answer. If no patch exists, it records `completion_rejected` and returns the missing evidence to the model, allowing at most two feedback rounds. Follow-up run `c365f47ac0c741878aa685216ca3882b` wrote a patch after this feedback and passed all hidden checks.

These are two development observations, not a statistically supported improvement claim. The general rule is tested with a provider that repeatedly claims it wrote a fix while never calling a write tool (`test_resilient_rejects_unwritten_fix`).

## 2. An MCP read timed out before execution

The fault injector raises a timeout on the first `repo__read_file` call. The resilient policy records the error and retries that read once. It never applies that automatic retry policy to mutations or shell commands, where an ambiguous timeout could duplicate an effect.

The checked-in [event export](evidence/mcp-timeout.json) shows one `tool_timeout`, a later successful read, a recorded patch, and successful independent grading. The provider is explicitly scripted in this scenario. This demonstrates recovery machinery, not a model's ability to recover from an arbitrary outage.

## 3. A worker died while holding a job lease

`test_worker_process_crash_and_recovery` starts a real Python subprocess, claims a job, records the injected fault, and exits immediately with code 77. The job initially remains running. After lease expiry, a replacement claims attempt two, records `attempt_interrupted`, executes in a new workspace, and completes the fixture.

Separate fencing tests prove the old owner cannot extend the new lease, append events, or publish completion. A regression test also covers cancellation followed by worker death, so that job is eventually reaped rather than remaining running indefinitely.

The [JUnit artifact](evidence/fault-scenarios.xml) records the fault scenarios. Container orphan cleanup has scoped unit coverage; live Docker cleanup after a crash still needs a Docker-enabled host.

## Development pilot exclusions

An early pilot was stopped after expected file errors were masked as MCP crashes and cancellation was wrapped in SDK exception groups. Its [summary](evidence/aborted-pilot-summary.json) is preserved and excluded from final benchmark claims. The harness now exposes actionable expected tool errors, preserves cancellation through nested groups, and can renew an expired lease only when the same owner/generation still holds it. Replacement-worker fencing remains enforced.
