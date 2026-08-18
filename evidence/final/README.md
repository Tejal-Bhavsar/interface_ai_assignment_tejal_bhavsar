# Final Evidence Bundle

This directory is generated from previously captured run evidence. Source evidence is left unchanged.

All member/account records in the local LegacyCore target are synthetic demonstration data.

## What to inspect

1. `01_discovery/` — genuine LLM-driven discovery evidence for the run referenced by the capability artifact.
2. `02_artifact/` — the saved typed/versioned reusable capability.
3. `03_replay_success/` — deterministic successful replay with checkpoint verification.
4. `04_business_outcome/` — known caller-visible business outcome.
5. `05_recovery/` — bounded deterministic recovery.
6. `06_hard_failure/` — hard failure with richer debug evidence.
7. `07_human_handoff/` — real same-session human takeover and automation resume.
8. `08_policy/` — global runtime policy block/escalation.
9. `09_agent_api/` — optional agent-facing capability invocation evidence.

## Integrity

`checksums.sha256` contains SHA-256 hashes for every copied file in this bundle except the checksum file itself.

## Selection manifest

`manifest.json` records which source run was selected for each proof category and whether any required evidence was missing.
