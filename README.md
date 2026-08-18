# Computer-Use Automation System

> **LLM-driven discovery. Typed capability compilation. Deterministic replay.**
>
> A focused implementation of a computer-use automation layer for legacy applications that do not expose APIs.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Browser-Playwright-2EAD33?logo=playwright&logoColor=white)
![Tests](https://img.shields.io/badge/tests-120%20passed-brightgreen)
![Status](https://img.shields.io/badge/status-complete-success)

This project implements the full record-once / replay-many workflow requested in the **interface.ai Computer-Use Automation take-home**.

The core idea is:

> **The model discovers. The artifact becomes a reusable capability. Deterministic replay is how an AI agent invokes it in production.**

The concrete demo target is **LegacyCore X**, a synthetic banking back-office application built to resemble a stable but imperfect legacy enterprise UI. All member names, IDs, balances, failures, and account data in the repository are synthetic.

---

## Table of contents

- [What this system does](#what-this-system-does)
- [End-to-end flow](#end-to-end-flow)
- [Assignment coverage](#assignment-coverage)
- [Quick start](#quick-start)
- [Run the full demo](#run-the-full-demo)
- [Architecture](#architecture)
- [Capability artifact](#capability-artifact)
- [Deterministic replay](#deterministic-replay)
- [Runtime outcomes and recovery](#runtime-outcomes-and-recovery)
- [Safety and policy](#safety-and-policy)
- [Sensitive-data handling](#sensitive-data-handling)
- [Human-in-the-loop handoff](#human-in-the-loop-handoff)
- [Multi-tenant design](#multi-tenant-design)
- [Agent-facing capability API](#agent-facing-capability-api)
- [Evidence](#evidence)
- [Tests](#tests)
- [Repository structure](#repository-structure)
- [Design trade-offs](#design-trade-offs)
- [Known limitations](#known-limitations)
- [What I would build next](#what-i-would-build-next)

---

## What this system does

The system takes a natural-language goal for a target application, uses an LLM to accomplish it once against the live UI, converts that successful run into a reusable typed capability, and then executes that capability deterministically on later invocations.

For the example capability:

```text
Goal:
Look up a member and return the current savings balance.

Discovery:
Gemini observes and operates the live LegacyCore UI.

Compiled capability:
lookup_savings_balance@1.0.0

Runtime input:
member_id

Runtime output:
current_savings_balance

Production execution:
ReplayEngine follows the saved capability with zero LLM decisions.
```

The implementation also covers:

- semantic/contextual target resolution,
- typed inputs and outputs,
- artifact integrity verification,
- checkpoint validation,
- business outcomes,
- bounded deterministic recovery,
- hard failures,
- configurable policy allowlists,
- risky/irreversible action handling,
- sensitive-data redaction,
- structured evidence,
- same-session human takeover and resume,
- tenant/application compatibility,
- and an agent-facing capability API.

---

## End-to-end flow

```text
             ┌───────────────────────────────┐
             │ Natural-language goal + URL   │
             └──────────────┬────────────────┘
                            │
                            ▼
             ┌───────────────────────────────┐
             │ Genuine LLM discovery         │
             │ observe → decide → act        │
             └──────────────┬────────────────┘
                            │
                            ▼
             ┌───────────────────────────────┐
             │ Successful DiscoveryRunResult │
             └──────────────┬────────────────┘
                            │
                            ▼
             ┌───────────────────────────────┐
             │ CapabilityCompiler            │
             │ parameterize + validate       │
             └──────────────┬────────────────┘
                            │
                            ▼
             ┌───────────────────────────────┐
             │ CapabilityArtifact            │
             │ typed + versioned + reviewable│
             └──────────────┬────────────────┘
                            │
                            ▼
             ┌───────────────────────────────┐
             │ Deterministic ReplayEngine    │
             │ NO LLM decisions              │
             └──────────────┬────────────────┘
                            │
                 ┌──────────┼───────────┐
                 │          │           │
                 ▼          ▼           ▼
             completed   business     recoverable /
                         outcome      hard failure
                                        │
                                        ▼
                                  human intervention
                                  when required
```

---

## Assignment coverage

| Requirement | Implementation | Proof |
|---|---|---|
| Goal + target input | `DiscoveryEngine.run(goal, entry_url)` | discovery evidence |
| Genuine LLM loop | observe → decide → act with live provider | `evidence/final/01_discovery/` |
| Real UI interaction | `PlaywrightSurface` | discovery/replay evidence |
| Typed reusable artifact | `CapabilityArtifact` | canonical JSON artifact |
| Parameterized inputs | `{{member_id}}` | compiled capability |
| Typed outputs | `current_savings_balance` | artifact/API contract |
| Stable targeting | role/name/label/text/relative locators | surface tests |
| Versioned/reviewable capability | identity + schema + approval state | artifact |
| Deterministic replay | `ReplayEngine` | replay evidence |
| Checkpoint | `OUTPUT_EXISTS(current_savings_balance)` | successful replay |
| Business outcome | `MEMBER_NOT_FOUND` | final evidence |
| Recoverable conditions | session/busy reload rules | final evidence |
| Hard failures | permission/app failures | screenshot + sanitized HTML |
| Explicit allowlist | `PolicyEngine` + `policy.json` | policy evidence |
| Risky/irreversible handling | human-required / blocked | policy tests |
| Data redaction | typed sensitivity + recursive sanitization | redaction tests |
| Structured observability | JSON + JSONL evidence | `evidence/` |
| Rich failure signal | masked PNG + sanitized structure | failure evidence |
| Human escalation | `InterventionRequest` | handoff evidence |
| Same-session takeover | same `Page` + `BrowserContext` | manual handoff proof |
| Human actions recorded | Playwright browser instrumentation | handoff evidence |
| Multi-tenant design | `TenantBindingRegistry` | tenancy tests |
| Surface abstraction | `ComputerSurface` | architecture |
| Agent-facing interface | FastAPI capability catalog/invocation | API evidence |
| Approval seam | draft blocked by default | replay/catalog tests |
| Final evidence bundle | audited + lineage-aware | `evidence/final/` |
| Automated validation | full pytest suite | **120 passed** |

---

# Quick start

## Prerequisites

- Python **3.11+**
- Playwright Chromium
- A live model API key only if you want to perform a **new genuine discovery**

The saved capability, deterministic replay, evidence inspection, mock-provider checks, and most tests do not require a live model service.

## 1. Create the environment

```bash
python -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

## 3. Install Chromium

```bash
python -m playwright install chromium
```

## 4. Start LegacyCore X

```bash
python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000
```

Open:

```text
http://127.0.0.1:8000/legacy
```

---

# Run the full demo

The assignment's main workflow can be demonstrated with two commands after the target server is running.

## A. Genuine LLM discovery → capability compilation

In another terminal:

```bash
source .venv/bin/activate

export CUA_LLM_PROVIDER=gemini

python -m scripts.smoke_compile
```

Also export the API-key environment variable configured for the selected provider in `config/llm.json`.

This command performs:

```text
goal
  ↓
live browser observation
  ↓
LLM chooses one typed action
  ↓
live target resolution
  ↓
policy evaluation
  ↓
browser action
  ↓
repeat
  ↓
successful discovery
  ↓
redacted discovery evidence
  ↓
capability compilation
  ↓
integrity verification
  ↓
saved capability
```

Output artifact:

```text
capabilities/lookup_savings_balance.v1.json
```

Discovery evidence:

```text
evidence/discovery/disc_<run-id>/
```

## B. Deterministic replay — no LLM

Keep LegacyCore running:

```bash
python -m scripts.smoke_replay
```

Replay uses the saved artifact and runtime inputs. It does **not** ask a model what to do.

---

# Architecture

The project is intentionally a **modular monolith**.

That keeps the take-home small while still exposing the architectural seams that would matter in a production system.

```text
┌───────────────────────┐
│      LLM Provider     │
│ Gemini/OpenAI/etc.    │
└──────────┬────────────┘
           │ discovery only
           ▼
┌───────────────────────┐
│    DiscoveryEngine    │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│    ComputerSurface    │◄──────── PlaywrightSurface
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│  CapabilityCompiler   │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│  CapabilityArtifact   │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│      ReplayEngine     │
│   deterministic only  │
└───────┬───────┬───────┘
        │       │
        │       ├──────── PolicyEngine
        │
        ├──────────────── EvidenceRecorder
        │
        └──────────────── HumanHandoff
```

## Main boundaries

### `ComputerSurface`

Abstracts the interaction medium away from the automation logic.

Current implementation:

```text
ComputerSurface
      ↓
PlaywrightSurface
```

Future implementations could use:

```text
accessibility APIs
native desktop automation
remote desktop
screenshots + coordinates
OCR / vision-based targeting
```

### `DiscoveryEngine`

The only production component allowed to use an LLM for action decisions.

### `CapabilityCompiler`

Converts a successful exploratory run into a strict reusable contract.

### `ReplayEngine`

Executes only the saved contract.

### `PolicyEngine`

Applies deployment-level safety rules independently from artifact-level safety.

### Evidence recorders

Observe and persist what happened but never choose the next action.

---

# Genuine discovery

The final canonical discovery included in the repository is:

```text
run_id:   disc_22b2281984ae
provider: gemini
model:    gemini-2.5-flash
status:   completed
```

The live model discovered:

```text
1. FILL    Member ID textbox
2. CLICK   Search
3. CLICK   Savings
4. EXTRACT Current Balance using same-row context
5. COMPLETE
```

The compiled artifact contains four executable steps because `COMPLETE` is discovery control flow rather than a reusable browser operation.

The discovery evidence includes events such as:

```text
discovery_started
policy_evaluated
observation
llm_decision
target_resolved
action_executed
...
discovery_finished
```

Raw page text and sensitive runtime values are not persisted.

---

# Target resolution

A target is represented by a `TargetDescriptor` containing ordered `LocatorCandidate`s.

Supported locator kinds include:

```text
ROLE
LABEL
TEXT
PLACEHOLDER
RELATIVE_TEXT
CSS
XPATH
```

The implementation prefers semantic/contextual locators.

The canonical capability uses:

| Target | Strategy |
|---|---|
| Member ID | role=`textbox`, name=`Member ID` |
| Search | role=`button`, name=`Search` |
| Savings | role=`link`, name=`Savings` |
| Balance | reference=`Current Balance`, relation=`same_row` |

The extracted balance is **not** located using the concrete discovered balance text because that value changes on every invocation.

## Ambiguity policy

A candidate must uniquely resolve.

The engine does not silently call `.first()` when multiple elements match.

```text
0 matches     → try next declared candidate / fail
1 match       → use it
>1 matches    → fail closed
```

---

# Capability artifact

The artifact is a **contract**, not a recorded transcript.

The canonical capability is:

```text
id:             lookup_savings_balance
version:        1.0.0
schema_version: 1.0
approval_state: draft

input:
  member_id

output:
  current_savings_balance

steps:
  4
```

Its current integrity SHA-256 is:

```text
cd2a9e2e522df917c914b5e1d1eb1f312ed171268f95b2dce8f976b82f50a6f5
```

## Artifact contents

Conceptually:

```text
CapabilityArtifact
├── schema_version
├── identity
│   ├── id
│   ├── name
│   ├── version
│   ├── description
│   └── approval_state
├── target
├── inputs
├── outputs
├── steps
├── business_outcomes
├── recoveries
├── failures
├── checkpoint
├── safety
├── discovery provenance
└── integrity_sha256
```

## Parameterization

The discovery value:

```text
1001
```

becomes:

```text
{{member_id}}
```

The concrete discovered balance is also excluded from the artifact.

## Compiler fail-closed checks

Compilation is rejected when, for example:

- discovery did not complete,
- no reusable operation exists,
- a declared input is unused,
- a dynamic extracted value would become a brittle locator,
- an expected output contract changes,
- sensitive runtime values would leak into the artifact.

---

# Deterministic replay

Replay deliberately has **no LLM decision loop**.

```text
load capability
      ↓
verify integrity
      ↓
check approval
      ↓
validate typed inputs
      ↓
bind placeholders
      ↓
validate artifact safety
      ↓
check runtime policy
      ↓
resolve target
      ↓
execute deterministic step
      ↓
classify runtime state
      ↓
recover / stop / continue
      ↓
verify checkpoint
      ↓
return structured result
```

## Replay status

Caller-visible status is one of:

```text
COMPLETED
BUSINESS_OUTCOME
FAILED
HUMAN_REQUIRED
```

A replay is not considered successful merely because every click happened.

The declared checkpoint must also pass.

Canonical checkpoint:

```text
OUTPUT_EXISTS(current_savings_balance)
```

---

# Runtime outcomes and recovery

LegacyCore intentionally includes runtime conditions that are more interesting than simple selector drift.

| State | Classification | Behavior |
|---|---|---|
| valid member | normal | continue |
| member missing | business outcome | return to caller |
| session expired | recoverable | bounded reload |
| transient busy | recoverable | bounded reload |
| permission denied | hard failure | stop |
| application error | hard failure | stop |
| security verification | human required | hand off |

## Why separate business outcomes?

`MEMBER_NOT_FOUND` is not an automation crash.

It is a valid domain result that an upstream agent needs to know.

## Why bound recovery?

Every recovery rule has a maximum number of attempts.

The system cannot retry indefinitely.

---

# Safety and policy

Safety is intentionally layered.

## Artifact safety

The capability describes the action/risk envelope it was designed and reviewed for.

## Deployment policy

`config/policy.json` independently controls:

- allowed origins,
- allowed route prefixes,
- allowed action types,
- risky phrases,
- blocked phrases,
- risky-action handling.

## Live-target policy checks

Policy evaluates the **actual resolved live control**.

For example:

```text
artifact description:
"Continue"

actual live button:
"Confirm Open Sub-Account"
```

The live target wins.

## Risk behavior

```text
SAFE         → may execute if allowed
RISKY        → HUMAN_REQUIRED
IRREVERSIBLE → BLOCK
blocked text → BLOCK
```

Blocked phrases take precedence over generic risky handling.

## URL containment

Checks occur:

1. before initial navigation,
2. before known external destinations,
3. after browser actions/recovery.

Route matching uses path boundaries so an allowlist for:

```text
/legacy
```

does not accidentally permit:

```text
/legacy-evil
```

---

# Sensitive-data handling

The system assumes UI state may contain regulated financial data.

## Typed sensitive fields

Examples:

```text
member_id
current_savings_balance
```

are marked sensitive.

## Artifact protection

Concrete discovery-time sensitive values are not embedded in the reusable capability.

## Replay evidence

The evidence layer redacts:

- sensitive input values,
- sensitive outputs,
- known runtime values,
- member IDs in URLs,
- sensitive query parameters.

## Screenshot protection

Before persistence, elements marked:

```css
[data-sensitive=true]
```

are masked.

## Discovery evidence

Discovery evidence intentionally avoids persisting:

```text
raw visible page text
raw LLM responses
concrete fill values
concrete extracted balances
```

Instead it stores safe proof such as:

```text
provider + model
sanitized URL/title
control metadata
character counts
observation fingerprint
typed LLM decision
resolved target metadata
policy decision
execution event
terminal status
```

---

# Human-in-the-loop handoff

The handoff mechanism is implemented as a real ownership transition.

Demonstrated case:

```text
Savings page
    ↓
security verification appears
    ↓
SECURITY_VERIFICATION
    ↓
automation pauses
    ↓
InterventionRequest
    ↓
ownership → HUMAN
    ↓
operator uses SAME browser
    ↓
operator acknowledges modal
    ↓
operator requests resume
    ↓
automation validates live state
    ↓
ownership → AUTOMATION
    ↓
replay continues
```

## Same session

The exact existing Playwright:

```text
Page
BrowserContext
```

are preserved.

A fresh browser is not created.

## Human actions

Human actions are captured in sanitized form.

The final manual proof records:

```text
click: Acknowledge & Continue
```

## Resume is not automatic

Pressing Enter only requests resume.

Automation first verifies:

- current URL remains allowed,
- blocker has disappeared,
- runtime state is acceptable,
- next-step conditions are satisfied,
- next target uniquely resolves.

Only then is automation allowed to take ownership again.

---

# Multi-tenant design

Capability logic is separated from deployment configuration.

```text
Capability = HOW
Binding    = WHERE
```

A binding can define:

```text
tenant ID
application key
entry URL
vendor product
compatibility key
enabled state
approved capability versions
```

The same artifact can be bound to multiple compatible institutions without mutation.

The tenancy layer fails closed when:

- the tenant is unknown,
- the application binding does not exist,
- the vendor/version is incompatible,
- the binding is disabled.

---

# Agent-facing capability API

The project implements the optional capability-interface stretch goal.

FastAPI endpoints include:

```text
GET  /health
GET  /v1/capabilities
GET  /v1/capabilities/{capability_id}?version=...
POST /v1/capabilities/{capability_id}/invoke
```

## Start the API

Terminal 1:

```bash
python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000
```

Terminal 2:

```bash
CUA_ALLOW_DRAFT_CAPABILITIES=1 \
python -m uvicorn apps.capability_api:app \
  --host 127.0.0.1 \
  --port 8011
```

## Discover capabilities

```bash
curl http://127.0.0.1:8011/v1/capabilities
```

## Invoke

```bash
curl -X POST \
  http://127.0.0.1:8011/v1/capabilities/lookup_savings_balance/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "version": "1.0.0",
    "tenant_id": "northstar-cu",
    "application_key": "member-servicing",
    "arguments": {
      "member_id": "1002"
    }
  }'
```

The service performs exact capability/version lookup, tenant compatibility checks, deterministic replay, and evidence generation.

---

# Running without a live model

A live model is required only to create a **new discovery**.

Existing saved capabilities can be replayed offline from model providers:

```bash
python -m scripts.smoke_replay
```

The provider abstraction can also be tested without an external service:

```bash
CUA_LLM_PROVIDER=mock \
python -m scripts.smoke_llm
```

---

# Evidence

The final reviewer-facing bundle is:

```text
evidence/final/
├── README.md
├── manifest.json
├── checksums.sha256
├── 01_discovery/
├── 02_artifact/
├── 03_replay_success/
├── 04_business_outcome/
├── 05_recovery/
├── 06_hard_failure/
├── 07_human_handoff/
├── 08_policy/
└── 09_agent_api/
```

## Selected final proof

| Category | Run |
|---|---|
| Genuine discovery | `disc_22b2281984ae` |
| Successful replay | `replay_b5da39f38b05` |
| Business outcome | `replay_4647a6ff59f6` |
| Recovery | `replay_b4775e61a9d5` |
| Hard failure | `replay_530635599c3d` |
| Real manual handoff | `replay_2d8ca6b9db94` |
| Runtime policy | `replay_7999ad388fd5` |
| Agent API | `replay_acf52073349e` |

## Audit the evidence

```bash
python -m scripts.consolidate_evidence --audit-only
```

## Rebuild the curated bundle

```bash
python -m scripts.consolidate_evidence
```

The bundler is non-destructive and checks:

- genuine non-mock discovery,
- canonical artifact lineage,
- required replay cases,
- real manual handoff rather than scripted regression,
- redaction,
- final manifest,
- final checksums.

---

# Tests

Run the full suite:

```bash
python -m pytest -v
```

Current result:

```text
120 passed, 1 warning
```

The warning is a third-party `google-genai` deprecation warning under Python 3.14 and does not represent a failed project test.

Coverage includes:

- typed models,
- provider normalization/adapters,
- discovery,
- compiler safety,
- deterministic replay,
- runtime classification,
- Playwright targeting,
- policy,
- redaction,
- evidence,
- handoff,
- tenant binding,
- capability catalog/API,
- final evidence bundling.

---

# Repository structure

<details>
<summary><strong>Expand repository tree</strong></summary>

```text
.
├── README.md
├── REPORT.md
├── requirements.txt
├── pyproject.toml
│
├── apps/
│   ├── server.py
│   └── capability_api.py
│
├── capabilities/
│   └── lookup_savings_balance.v1.json
│
├── config/
│   ├── llm.json
│   ├── app_profiles.json
│   ├── policy.json
│   └── tenant_bindings.json
│
├── cua/
│   ├── models.py
│   ├── surface.py
│   ├── playwright_surface.py
│   ├── discovery.py
│   ├── discovery_evidence.py
│   ├── compiler.py
│   ├── replay.py
│   ├── profiles.py
│   ├── policy.py
│   ├── redaction.py
│   ├── evidence.py
│   ├── handoff.py
│   ├── playwright_handoff.py
│   ├── tenancy.py
│   ├── capability_catalog.py
│   ├── capability_service.py
│   ├── evidence_bundle.py
│   └── llm/
│
├── scripts/
│   ├── smoke_playwright.py
│   ├── smoke_llm.py
│   ├── smoke_discovery.py
│   ├── smoke_compile.py
│   ├── smoke_compile_offline.py
│   ├── smoke_replay.py
│   ├── smoke_replay_runtime.py
│   ├── smoke_evidence.py
│   ├── smoke_handoff.py
│   ├── smoke_tenancy.py
│   ├── smoke_capability_api.py
│   ├── smoke_policy.py
│   └── consolidate_evidence.py
│
├── tests/
│
└── evidence/
    ├── discovery/
    ├── replay/
    ├── policy/
    ├── agent_api/
    └── final/
```

</details>

---

# Useful commands

<details>
<summary><strong>Expand smoke/demo commands</strong></summary>

### Browser surface

```bash
python -m scripts.smoke_playwright
```

### Mock LLM provider

```bash
CUA_LLM_PROVIDER=mock \
python -m scripts.smoke_llm
```

### Genuine discovery

```bash
CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_discovery
```

### Genuine discovery + compile

```bash
CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_compile
```

### Deterministic replay

```bash
python -m scripts.smoke_replay
```

### Runtime taxonomy

```bash
python -m scripts.smoke_replay_runtime
```

### Evidence

```bash
python -m scripts.smoke_evidence
```

### Real manual handoff

```bash
python -m scripts.smoke_handoff
```

### Scripted handoff regression

```bash
python -m scripts.smoke_handoff --auto
```

### Tenant binding

```bash
python -m scripts.smoke_tenancy
```

### Agent-facing capability interface

```bash
python -m scripts.smoke_capability_api
```

### Runtime policy

```bash
python -m scripts.smoke_policy
```

</details>

---

# Design trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| LLM only in discovery | predictable/cheap/auditable replay | no automatic reasoning around unknown drift |
| Capability instead of transcript | clean reusable contract | requires strict compilation |
| Semantic targets first | more stable than raw selectors | hostile UIs may require other surfaces |
| Reject ambiguity | safer for financial automation | some recoverable cases stop earlier |
| Embed app runtime semantics | deterministic error handling | profile/capability must evolve with vendor changes |
| Separate global policy | deployment rules evolve independently | two safety layers to maintain |
| Keep same browser for handoff | preserves real session state | requires session-aware operator flow |
| Modular monolith | focuses effort on correctness | no distributed production runtime |

---

# Known limitations

The following are deliberate cuts, not hidden production claims:

- only the browser `ComputerSurface` is implemented,
- no VNC/co-browsing operator product,
- no persistent database-backed capability registry,
- no queue/worker/cluster infrastructure,
- no RBAC/SSO,
- no external secrets-manager integration,
- no full approval workflow,
- no automatic LLM repair during deterministic replay,
- no fleet-scale drift telemetry,
- no multi-run reliability score,
- no code-generation stretch goal.

One important integration limit:

> Runtime `HUMAN_REQUIRED` is connected to the real same-session handoff flow. A policy-produced `HUMAN_REQUIRED` currently returns a structured terminal result before the risky action rather than entering the same persistent handoff channel automatically.

That boundary is documented intentionally rather than hidden.

---

# What I would build next

1. **Unify all human-required states** behind one durable intervention/session service.
2. Add a persistent **capability/version/approval registry**.
3. Implement a second, non-DOM `ComputerSurface`.
4. Add vendor/tenant compatibility and drift telemetry.
5. Add a reviewed re-discovery/versioning workflow.
6. Add multi-run stability/confidence metrics.
7. Build an operator-facing intervention queue/UI.

I would keep the default replay path deterministic.

If a reviewed capability becomes unsafe or ambiguous, the preferred behavior is:

```text
stop
  ↓
preserve evidence
  ↓
review / rediscover
  ↓
publish a new capability version
```

rather than silently putting an LLM back into production execution.

---

## Final project status

```text
Genuine LLM discovery            ✅
Typed capability                 ✅
Parameterized runtime input      ✅
Typed output                     ✅
Deterministic replay             ✅
Checkpoint verification          ✅
Business-outcome handling        ✅
Bounded recovery                 ✅
Hard-failure evidence            ✅
Same-session manual handoff      ✅
Human-action capture             ✅
Runtime safety policy            ✅
Sensitive-data redaction         ✅
Multi-tenant binding             ✅
Agent-facing capability API      ✅
Curated final evidence bundle    ✅
120 automated tests passing      ✅
```

For the detailed architectural reasoning and explicit cut lines, see **[`REPORT.md`](REPORT.md)**.
