# Evidence-backed project description

**HarnessLab — Coding-Agent Evaluation and Reliability Platform**

- Built a Python evaluation platform with stdio MCP tool servers, independent patch grading, durable worker leases, and a React trace viewer.
- Curated and validated 30 authored regression tasks across three licensed Python libraries, freezing separate development and held-out sets with reproducible source snapshots.
- Implemented atomic experiment budgets and stale-worker fencing in PostgreSQL; verified concurrent claims, crash recovery, cancellation, and grading with a real local database.
- Added free local-model inference and macOS process isolation; diagnosed a real agent's empty-patch completion claim and verified a follow-up fix using hidden tests.

Add held-out success-rate, cost, and latency measurements only after the final study completes. Do not describe the scripted provider as model performance or the synthetic tasks as historical upstream issues. Docker and browser verification remain separate completion gates.
