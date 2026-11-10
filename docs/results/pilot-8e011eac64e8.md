# Development pilot: local Qwen3

Experiment `8e011eac64e8401e8d35b28283cce91f` · published 2026-11-09T13:22:47.541406+00:00

This is a measured local-model study. Synthetic fixture results are not included. These development results are not a held-out performance claim.

- Tasks: 5; repetitions per configuration: 1.
- Backend: `macos`; source fingerprint: `2a66c69743295e94ff22e6834f037abaef8731b43d4daa90a7f2ce9737b9cdf1`.
- Model: `qwen3-4b-instruct-2507-q8_0`; provider API charges: $0 (local inference).
- Seed: 42; fixed-seed repetitions measure repeatability, not independent stochastic samples.

| Configuration | Finished | Valid trials | Solved | Success | Infra errors | Median seconds | p95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline `02b8b004` | 5/5 | 4 | 0 | 0.0% | 1 | 139.98 | 208.18 |
| resilient `dd5299fa` | 5/5 | 4 | 0 | 0.0% | 1 | 151.26 | 204.93 |

Valid trials include solved, unsolved, and budget-exceeded outcomes. Infrastructure errors and cancelled jobs are excluded from the success denominator and remain in the raw results. Latencies reflect this host and may include infrastructure noise.

## Paired outcomes

- Common tasks: 4; balanced trial counts: True.
- Resilient better: 0; baseline better: 0; ties: 4.
- Mean task-level success difference (resilient minus baseline): 0.00.

No significance claim is made. Task-level pairing keeps repeated trials together; descriptive trial-level intervals are available in the raw export.

## Failure evidence

Outcomes: budget_exceeded=2, infrastructure_error=2, unsolved=6.

| Task | Harness | Outcome | Added lines | Deleted lines |
| --- | --- | --- | ---: | ---: |
| boltons-split-iter | baseline | budget_exceeded | 0 | 0 |
| boltons-split-iter | resilient | budget_exceeded | 0 | 0 |
| inflection-dasherize | baseline | unsolved | 4 | 405 |
| inflection-dasherize | resilient | unsolved | 4 | 405 |
| more-itertools-take | baseline | unsolved | 12 | 1583 |
| more-itertools-take | resilient | unsolved | 12 | 1583 |
| boltons-lstrip-iter | baseline | infrastructure_error | 0 | 0 |
| boltons-lstrip-iter | resilient | infrastructure_error | 0 | 0 |
| inflection-humanize | baseline | unsolved | 16 | 417 |
| inflection-humanize | resilient | unsolved | 16 | 417 |

A nonempty patch is not sufficient evidence of correctness. The grader's original regression tests and hidden checks decide the outcome; large deletions are retained for diagnosis rather than counted as successful fixes.

Known API spend: $0.0000; unsettled calls: 2; reserved uncertain API spend: $0.0000.

[Raw runs, traces, configuration hashes, and paired outcomes](pilot-8e011eac64e8.json)
