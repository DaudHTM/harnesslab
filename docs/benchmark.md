# Benchmark protocol

## Frozen corpus

The catalog contains 30 authored regression tasks across pinned versions of boltons, more-itertools, and inflection: ten development tasks and twenty held out. Each deliberately introduces a mutation into real library code. None is represented as a historical upstream issue.

Every agent snapshot has one initial Git commit containing the broken source. Upstream Git history, reference patches, and HarnessLab files are absent. The grader applies the candidate patch to a fresh snapshot and runs hidden contract tests plus a copied, licensed upstream regression module. Validation requires a failing test exit code on the base and a passing reference patch.

`benchmarks/catalog.json` freezes snapshot commits and hidden-test/reference-patch hashes. `benchmarks/validation.json` records all thirty base/reference validations under the named backend. `scripts/build_corpus.py --fetch` recreates the source snapshots and retains licenses.

The separate normalization fixture and scripted provider test infrastructure. The fake provider is rejected for corpus tasks.

## Free local-model study

The selected model is Qwen3-4B-Instruct-2507 Q8_0, served by a pinned llama.cpp binary. Downloads are checksum verified. Local inference has no provider API charge. Candidate commands require Docker or native macOS isolation; real models cannot use unsafe local mode.

1. Run five development tasks across the repositories with each harness. Verify budgets, tool behavior, grading, and failure classification.
2. Freeze source and configuration fingerprints before held-out evaluation. Runtime code drift invalidates an existing study instead of mixing implementations.
3. Run twenty held-out tasks three times per configuration using the same model, limits, and seed: 120 primary trials.
4. Publish raw results, task-level paired outcomes, infrastructure failures, known/uncertain costs, and median/p95 latency. Record model checksum/revision, harness fingerprint, and execution backend.
5. Include failed runs and explain exclusions. Improvement claims require measured evidence.

The resilient harness adds context compaction, bounded transient-read and rate-limit retries, and an empty-patch completion check. It returns evidence to a model that claims completion without modifying the workspace.

## Interpretation limits

- Small authored mutations do not substitute for a broad real-world SWE benchmark.
- Public upstream code and fixes may be in model training; public task construction is also susceptible to contamination.
- Fixed-seed repetitions assess repeatability, not independent stochastic samples.
- Trial-level Wilson intervals are descriptive. Paired reports keep repeated trials together by task and make no significance claim.
- Synthetic fault tests measure infrastructure behavior, not learned prompt-injection resistance.
- Pilot findings are development evidence; held-out results are reported separately.
