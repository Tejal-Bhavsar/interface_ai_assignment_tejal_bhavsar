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
- [Guided execution walkthrough](#guided-execution-walkthrough)
- [Reviewer re-verification matrix](#reviewer-re-verification-matrix)
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


# Model-provider validation status

The provider layer is intentionally model-agnostic, but I distinguish between **implemented** and **live end-to-end validated** providers.

| Provider | Adapter implemented | Unit/provider contract tested | Full live discovery validated |
|---|---:|---:|---:|
| Gemini | ✅ | ✅ | ✅ |
| OpenAI | ✅ | ✅ | Not run live |
| Anthropic | ✅ | ✅ | Not run live |
| Grok / xAI | ✅ | ✅ | Not run live |
| Ollama | ✅ | ✅ | Not run end-to-end for final proof |
| OpenAI-compatible | ✅ | ✅ | Not run live |
| Mock | ✅ | ✅ | deterministic test provider |

The **canonical end-to-end discovery flow in this repository was run and verified with:**

```text
provider: gemini
model:    gemini-2.5-flash
run_id:   disc_22b2281984ae
status:   completed
```

That run is the live-model proof used by the compiled capability and final evidence bundle.

The other provider adapters are real implementations rather than empty placeholders: they have provider-specific request/response handling and are covered by mocked/unit contract tests. However, I did **not** claim full live end-to-end validation for every paid provider because doing so would require separate API credentials/usage for each service and was outside the budget of this take-home.

This distinction is intentional:

```text
Implemented provider adapter
        ≠
Live end-to-end production validation
```

For the assignment's required genuine discovery proof, Gemini 2.5 Flash is the validated path.


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



# Reviewer re-verification matrix

This table maps the **original implementation steps** to the exact command a reviewer can run to verify each layer.

> **Before Steps 7–18:** keep LegacyCore X running in a separate terminal:
>
> ```bash
> python -m uvicorn apps.server:app \
>   --host 127.0.0.1 \
>   --port 8000
> ```

| Project step | What is being verified | Exact command | Requires live Gemini? | Main expected result | Output used by |
|---|---|---|---:|---|---|
| Step 7 | Playwright / `ComputerSurface` integration | `python -m scripts.smoke_playwright` | No | LegacyCore observed and semantic controls found | discovery/replay layer |
| Step 8 | Provider abstraction / typed LLM action contract | `CUA_LLM_PROVIDER=mock python -m scripts.smoke_llm` | No | valid typed mock action | validates provider seam |
| Step 9 | Genuine LLM discovery only | `CUA_LLM_PROVIDER=gemini python -m scripts.smoke_discovery` | **Yes** | completed live discovery + discovery evidence | optional standalone discovery proof |
| Step 10 | Genuine discovery **plus capability compilation** | `CUA_LLM_PROVIDER=gemini python -m scripts.smoke_compile` | **Yes** | completed discovery + `lookup_savings_balance.v1.json` | Step 11+ |
| Step 11 | Deterministic happy-path replay | `python -m scripts.smoke_replay` | No | completed replay + checkpoint + output | proves production replay |
| Step 12 | Runtime outcomes / recovery / failures | `python -m scripts.smoke_replay_runtime` | No | business outcome, recoverable, hard-failure classifications | error taxonomy proof |
| Step 13 | Replay evidence / observability | `python -m scripts.smoke_evidence` | No | success/recovery/failure evidence directories | Step 18 bundle |
| Step 14 | Real same-session human handoff | `python -m scripts.smoke_handoff` | No | human intervention, manual click, validated resume, completed replay | Step 18 bundle |
| Step 15 | Multi-tenant artifact reuse | `python -m scripts.smoke_tenancy` | No | same artifact binds to compatible tenants; incompatible tenant fails closed | architecture proof |
| Step 16 | Agent-facing capability API | `python -m scripts.smoke_capability_api` | No | catalog discovery + typed invocation + evidence run | optional stretch proof |
| Step 17 | Production runtime policy | `python -m scripts.smoke_policy` | No | allowed / blocked / human-required policy cases | Step 18 bundle |
| Step 18a | Audit evidence completeness | `python -m scripts.consolidate_evidence --audit-only` | No | `ALL REQUIRED EVIDENCE FOUND ✅` | determines bundle readiness |
| Step 18b | Build final reviewer evidence | `python -m scripts.consolidate_evidence` | No | `MISSING REQUIREMENTS: 0` + `evidence/final/` | submission evidence |
| Final regression | Entire automated test suite | `python -m pytest -v` | No | `120 passed` | final correctness check |

## Recommended reviewer command sequence

For a **full re-verification from the beginning**, use two terminals.

### Terminal 1 — keep LegacyCore running

```bash
source .venv/bin/activate

python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000
```

Leave this process running.

### Terminal 2 — verify each project step

```bash
source .venv/bin/activate
```

#### Step 7 — browser surface

```bash
python -m scripts.smoke_playwright
```

Expected high-level proof:

```text
LegacyCore page loads
Member ID textbox found
Search button found
browser interaction succeeds
```

#### Step 8 — provider abstraction

```bash
CUA_LLM_PROVIDER=mock \
python -m scripts.smoke_llm
```

Expected high-level proof:

```text
provider selected
typed AgentAction produced
normalization/provider seam works
```

#### Step 9 — standalone genuine discovery

```bash
CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_discovery
```

Expected high-level proof:

```text
PROVIDER: gemini
MODEL: gemini-2.5-flash
STATUS: completed
DISCOVERY EVIDENCE: evidence/discovery/disc_<run-id>
```

**Note:** this consumes a live model API call. A reviewer does not need to run both Step 9 and Step 10 unless they want to verify discovery separately.

#### Step 10 — genuine discovery + compile

```bash
CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_compile
```

Expected high-level proof:

```text
STEP 10 — REAL DISCOVERY → CAPABILITY COMPILATION
PROVIDER: gemini
MODEL: gemini-2.5-flash
STATUS: completed

ID: lookup_savings_balance
VERSION: 1.0.0
INPUTS: ['member_id']
OUTPUTS: ['current_savings_balance']
STEPS: 4
INTEGRITY VALID: True
```

Main generated files:

```text
evidence/discovery/disc_<run-id>/
capabilities/lookup_savings_balance.v1.json
```

**Why this matters:** the artifact created here is the direct input to Steps 11–17.

#### Step 11 — deterministic replay

```bash
python -m scripts.smoke_replay
```

Expected high-level proof:

```text
status: completed
checkpoint: True
current_savings_balance returned
zero LLM decisions
```

#### Step 12 — runtime taxonomy

```bash
python -m scripts.smoke_replay_runtime
```

Expected high-level proof:

```text
business outcome detected
recoverable condition recovered
hard failure stopped cleanly
human-required state recognized
```

#### Step 13 — evidence / observability

```bash
python -m scripts.smoke_evidence
```

Expected output directories:

```text
evidence/replay/replay_<success-id>/
evidence/replay/replay_<recovery-id>/
evidence/replay/replay_<failure-id>/
```

Expected failure evidence may include:

```text
failure_<step>.png
failure_<step>.html
```

#### Step 14 — same-session human handoff

```bash
python -m scripts.smoke_handoff
```

When the terminal reports:

```text
HUMAN INTERVENTION REQUIRED
```

use the **already-open browser** and click:

```text
Acknowledge & Continue
```

Then return to the terminal and press Enter to request resume.

Expected proof:

```text
STATUS: completed
CHECKPOINT: True
INTERVENTIONS: 1
RESUME ATTEMPTS: 1
HUMAN ACTIONS: 1
```

Do not use `--auto` for the reviewer-facing manual proof.

#### Step 15 — multi-tenant reuse

```bash
python -m scripts.smoke_tenancy
```

Expected proof:

```text
same capability artifact
→ compatible tenant A
→ compatible tenant B

incompatible tenant/version
→ rejected
```

#### Step 16 — agent-facing capability API

```bash
python -m scripts.smoke_capability_api
```

Expected proof:

```text
capability discovered
typed input/output contract exposed
exact version invoked
tenant binding applied
deterministic replay completed
evidence_run_id returned
```

#### Step 17 — runtime policy

```bash
python -m scripts.smoke_policy
```

Expected proof:

```text
NORMAL REPLAY:
completed

OUT-OF-SCOPE ROUTE:
failed POLICY_URL_BLOCKED

RISKY LIVE TARGET:
human_required POLICY_HUMAN_REQUIRED

BLOCKED LIVE TARGET:
failed POLICY_BLOCKED_PHRASE
```

Also expect checks such as:

```text
CONFIGURED ORIGIN/ROUTE ALLOWLIST ✅
ACTUAL LIVE TARGET EVALUATED ✅
RISKY ACTION → HUMAN_REQUIRED ✅
BLOCKED ACTION → FAILED CLOSED ✅
POST-ACTION URL CONTAINMENT ✅
ZERO LLM POLICY DECISIONS ✅
```

#### Step 18a — evidence audit

```bash
python -m scripts.consolidate_evidence --audit-only
```

Expected proof:

```text
DISCOVERY              found
REPLAY SUCCESS         found
BUSINESS OUTCOME       found
RECOVERY               found
HARD FAILURE           found
HUMAN HANDOFF          found
POLICY                 found
AGENT API              found

ALL REQUIRED EVIDENCE FOUND ✅
```

#### Step 18b — final evidence bundle

```bash
python -m scripts.consolidate_evidence
```

Expected proof:

```text
FINAL EVIDENCE BUNDLE: .../evidence/final
MISSING REQUIREMENTS: 0

SOURCE EVIDENCE LEFT UNCHANGED ✅
CANONICAL ARTIFACT COPIED ✅
REPLAY REDACTION AUDITED ✅
MANIFEST GENERATED ✅
BUNDLE CHECKSUMS GENERATED ✅
```

#### Final regression

```bash
python -m pytest -v
```

Current validated result:

```text
120 passed, 1 warning
```

## Minimal reviewer path

A reviewer who wants to verify the core assignment without running every internal smoke script can use:

```bash
# Terminal 1
python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000
```

Then:

```bash
# Terminal 2

# 1. Genuine discovery + compile
CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_compile

# 2. Deterministic replay
python -m scripts.smoke_replay

# 3. Error/evidence cases
python -m scripts.smoke_evidence

# 4. Real same-session human handoff
python -m scripts.smoke_handoff

# 5. Runtime policy
python -m scripts.smoke_policy

# 6. Final evidence audit
python -m scripts.consolidate_evidence --audit-only

# 7. Full automated suite
python -m pytest -v
```

That sequence demonstrates the assignment's main thread:

```text
real LLM discovery
        ↓
saved typed capability
        ↓
deterministic replay
        ↓
runtime error handling
        ↓
same-session human handoff
        ↓
policy / safety
        ↓
evidence
        ↓
automated regression
```

## Re-verifying without spending model budget

The repository already contains the canonical live Gemini discovery evidence and compiled artifact.

If the reviewer wants to verify all **post-discovery behavior without making another paid model call**, they can skip Steps 9 and 10 and use the committed artifact:

```text
capabilities/lookup_savings_balance.v1.json
```

Then run:

```bash
python -m scripts.smoke_replay
python -m scripts.smoke_replay_runtime
python -m scripts.smoke_evidence
python -m scripts.smoke_handoff
python -m scripts.smoke_tenancy
python -m scripts.smoke_capability_api
python -m scripts.smoke_policy
python -m scripts.consolidate_evidence --audit-only
python -m pytest -v
```

The committed discovery evidence under `evidence/final/01_discovery/` shows the genuine Gemini run that produced the canonical capability.


# Guided execution walkthrough

This section is the **full runbook from a clean checkout to final submission evidence**.

You do not need every smoke script just to see the main idea. The shortest required path is:

```text
1. Start LegacyCore
2. Run genuine discovery + compilation
3. Replay the saved artifact deterministically
```

The longer walkthrough below explains the purpose of every major validation step.

> **Legend**
>
> **Required path** — directly demonstrates a core assignment requirement.  
> **Validation** — proves an implementation boundary or failure mode.  
> **Stretch** — demonstrates an optional extension.

---

## Step 0 — enter the project and activate the environment

### Why this step exists

All following commands assume you are in the repository root and using the project virtual environment.

### Command

```bash
cd interface_ai_assignment_tejal_bhavsar
source .venv/bin/activate
```

If the environment does not exist yet:

```bash
python -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m playwright install chromium
```

### Expected result

Your shell should show the virtual environment as active, for example:

```text
(.venv) ...
```

### What this output is used for

Nothing is persisted from this step. It only ensures every later script runs with the repository's Python dependencies and Playwright installation.

---

## Step 1 — start the synthetic legacy application

**Type:** Required path

### Why this step exists

Discovery and replay must operate against a **real live UI**. `apps.server` provides the synthetic LegacyCore X application used throughout the assignment.

### Command

Run this in Terminal 1 and leave it running:

```bash
python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000
```

### Expected result

Uvicorn should start successfully and report that it is serving on:

```text
http://127.0.0.1:8000
```

The target UI is:

```text
http://127.0.0.1:8000/legacy
```

You can open that URL manually in a browser.

### What this output is used for

Every browser-based command below uses this running server:

```text
smoke_playwright
smoke_discovery
smoke_compile
smoke_replay
smoke_replay_runtime
smoke_evidence
smoke_handoff
smoke_policy
smoke_capability_api
```

If the LegacyCore server is not running, those scripts cannot interact with the target application.

---

## Step 2 — verify the browser surface

**Type:** Validation

### Why this step exists

Before involving an LLM, this proves the lower-level browser automation abstraction can:

```text
launch Chromium
navigate
observe the live page
identify semantic controls
interact with LegacyCore
```

This isolates Playwright/surface problems from LLM problems.

### Command

In Terminal 2:

```bash
python -m scripts.smoke_playwright
```

### Expected result

The script should identify the LegacyCore search page and controls such as:

```text
TITLE: LegacyCore Search
URL:   http://127.0.0.1:8000/legacy

controls:
- Member ID textbox
- Search button
```

It should also demonstrate navigation after searching a member.

### What this output is used for

No capability is created here.

The value of this step is diagnostic:

```text
If this fails:
fix browser/surface setup first.

If this passes:
the live UI interaction layer is working,
so discovery failures can be debugged separately.
```

---

## Step 3 — verify the LLM provider contract without using a live model

**Type:** Validation

### Why this step exists

The discovery engine expects model providers to return a **typed `AgentAction` contract**.

Before spending a live API call, the mock provider can prove that provider selection, normalization, and action conversion work.

### Command

```bash
CUA_LLM_PROVIDER=mock \
python -m scripts.smoke_llm
```

### Expected result

The output should show:

```text
PROVIDER: mock
```

and a valid typed action proposal.

### What this output is used for

This step does not produce the final discovery evidence.

It validates the provider seam:

```text
provider config
      ↓
provider factory
      ↓
typed LLM proposal
      ↓
AgentAction
```

The assignment's required proof still comes from a genuine live-model run in Step 4.

---

## Step 4 — run genuine LLM discovery and compile the capability

**Type:** Required path

### Why this step exists

This is the heart of the assignment.

The final validated live path uses **Gemini 2.5 Flash**. Other provider adapters are implemented and contract-tested, but they were not all exercised as separate paid end-to-end discovery runs because of budget constraints.

The system must prove that an actual LLM can:

```text
observe the live UI
decide what to do
act on the real surface
repeat until the goal is complete
```

A successful run is then converted into a reusable capability artifact.

### Configure the provider

Example:

```bash
export CUA_LLM_PROVIDER=gemini
```

Also make sure the provider's API-key environment variable is available locally.

For this repository, keys belong in the ignored local `.env` or your shell environment. They must never be committed.

### Command

```bash
CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_compile
```

### What happens internally

```text
1. create live LLM provider
2. create PolicyEngine
3. open PlaywrightSurface
4. observe LegacyCore
5. ask Gemini for one typed action
6. resolve the proposed target against the live page
7. evaluate policy
8. execute the browser action
9. repeat
10. complete the goal
11. persist privacy-aware discovery evidence
12. compile the successful discovery
13. parameterize concrete runtime inputs
14. reject sensitive runtime leakage
15. compute integrity SHA-256
16. save the capability artifact
```

### Expected console result

You should see a successful discovery similar to:

```text
PROVIDER: gemini
MODEL: gemini-2.5-flash

RUN ID: disc_<new-id>
STATUS: completed
```

The discovered flow should resemble:

```text
1. fill Member ID
2. click Search
3. click Savings
4. extract Current Balance
5. complete
```

The compiler should then report:

```text
ID: lookup_savings_balance
VERSION: 1.0.0
INPUTS: ['member_id']
OUTPUTS: ['current_savings_balance']
STEPS: 4
INTEGRITY VALID: True
```

### Files created

#### Discovery evidence

```text
evidence/discovery/disc_<run-id>/
├── metadata.json
├── events.jsonl
└── result.json
```

#### Capability

```text
capabilities/lookup_savings_balance.v1.json
```

### What those outputs are used for

The discovery evidence proves the required genuine observe → decide → act run happened.

The capability becomes the input to deterministic replay:

```text
genuine discovery
      ↓
CapabilityArtifact
      ↓
ReplayEngine
```

The artifact's `discovery.run_id` links it back to the exact discovery evidence that produced it.

---

## Step 5 — inspect the compiled capability

**Type:** Validation

### Why this step exists

The artifact is the most important output of discovery. It should be understandable without reading the model transcript.

### Command

```bash
python -m json.tool \
  capabilities/lookup_savings_balance.v1.json
```

### What to look for

You should see:

```text
identity
inputs
outputs
steps
business_outcomes
recoveries
failures
checkpoint
safety
discovery
integrity_sha256
```

The runtime member ID should appear as a placeholder:

```text
{{member_id}}
```

The concrete discovery member ID and concrete balance should **not** be embedded as reusable automation data.

### What this output is used for

This artifact is consumed by:

```text
smoke_replay
smoke_replay_runtime
smoke_evidence
smoke_handoff
smoke_tenancy
smoke_capability_api
smoke_policy
```

It is also copied into the final evidence bundle.

---

## Step 6 — deterministic happy-path replay

**Type:** Required path

### Why this step exists

This proves the production execution model:

> Given a saved artifact and new input parameters, perform the task **without asking an LLM what to do**.

### Command

```bash
python -m scripts.smoke_replay
```

### What happens internally

```text
load capability
      ↓
verify SHA integrity
      ↓
validate approval/input contract
      ↓
bind {{member_id}}
      ↓
navigate to configured target
      ↓
resolve saved semantic targets
      ↓
apply safety + policy
      ↓
execute the recorded steps
      ↓
extract declared output
      ↓
verify checkpoint
      ↓
return ReplayResult
```

### Expected result

The result should be equivalent to:

```text
status: completed
checkpoint: True

outputs:
{
  "current_savings_balance": "..."
}
```

The important fact is not the specific synthetic balance.

The important proof is:

```text
saved artifact + new runtime input
        ↓
same flow executes successfully
        ↓
declared output returned
        ↓
checkpoint passes
        ↓
zero LLM decisions
```

### What this output is used for

This proves deterministic replay independently from the discovery model.

The evidence version of this path is generated in Step 8.

---

## Step 7 — exercise the runtime error taxonomy

**Type:** Required-path validation

### Why this step exists

A real integration layer cannot treat every non-happy-path result as the same error.

This script exercises the runtime classifier and demonstrates deliberate handling of:

```text
business outcome
recoverable condition
hard failure
human-required state
```

### Command

```bash
python -m scripts.smoke_replay_runtime
```

### Expected result

You should see multiple scenarios classified into statuses such as:

```text
COMPLETED
BUSINESS_OUTCOME
FAILED
HUMAN_REQUIRED
```

Representative semantics:

```text
member not found
    → business outcome

session expired / transient busy
    → bounded deterministic recovery

permission denied / application error
    → hard failure

security verification
    → human required
```

### What this output is used for

These semantics are used by normal replay and are persisted into evidence in Step 8.

---

## Step 8 — generate replay observability evidence

**Type:** Required path

### Why this step exists

The assignment requires enough evidence to understand what happened during replay and at least one richer failure signal.

### Command

```bash
python -m scripts.smoke_evidence
```

### Expected result

The script creates separate evidence runs for:

```text
successful replay
recoverable replay
hard failure
```

You should see output paths resembling:

```text
SUCCESS EVIDENCE:
.../evidence/replay/replay_<id>

RECOVERY EVIDENCE:
.../evidence/replay/replay_<id>

FAILURE EVIDENCE:
.../evidence/replay/replay_<id>
```

### Files created

Typical successful/recovery run:

```text
evidence/replay/replay_<id>/
├── metadata.json
├── artifact.json
├── events.jsonl
└── result.json
```

A failure run can additionally contain:

```text
failure_<step>.png
failure_<step>.html
```

### What each file is for

| File | Purpose |
|---|---|
| `metadata.json` | run identity/context |
| `artifact.json` | exact capability used |
| `events.jsonl` | ordered execution/policy/recovery events |
| `result.json` | structured terminal result |
| `failure_*.png` | masked visual debugging signal |
| `failure_*.html` | sanitized structural debugging signal |

### What these outputs are used for

The final evidence bundler later selects canonical proof from these source runs.

---

## Step 9 — perform the real same-session human handoff

**Type:** Required path

### Why this step exists

The assignment requires more than returning `"human_required"`.

A human must be able to take over the **same live session**, act, and hand control back.

### Command

```bash
python -m scripts.smoke_handoff
```

### What happens

The script uses the synthetic security-verification member.

The flow should reach:

```text
HUMAN INTERVENTION REQUIRED
```

The terminal will explain that the human now owns the live browser session.

Use the **already-open Chromium window**.

Click:

```text
Acknowledge & Continue
```

Then return to the terminal and press Enter to **request resume validation**.

### Expected result

After validation you should see a result similar to:

```text
STATUS: completed
CHECKPOINT: True
INTERVENTIONS: 1
RESUME ATTEMPTS: 1
HUMAN ACTIONS: 1
```

and a captured human action such as:

```text
click: Acknowledge & Continue
```

### What this output proves

```text
automation paused                  ✅
ownership changed to HUMAN        ✅
same Page object preserved        ✅
same BrowserContext preserved     ✅
human action recorded             ✅
resume was requested              ✅
resume state was validated        ✅
automation resumed safely         ✅
```

### Evidence created

```text
evidence/replay/replay_<handoff-id>/
```

### What this output is used for

The final evidence audit specifically requires a **real manual** handoff run.

The optional command:

```bash
python -m scripts.smoke_handoff --auto
```

is useful for unattended regression, but it does **not** replace the manual proof.

---

## Step 10 — validate multi-tenant reuse

**Type:** Validation

### Why this step exists

The artifact should describe **how** to perform the task without hardcoding one institution's deployment details.

### Command

```bash
python -m scripts.smoke_tenancy
```

### Expected result

The smoke should demonstrate that:

```text
same artifact
    ↓
binds to northstar-cu
    ↓
binds to harbor-cu
```

while an incompatible future application/version fails closed.

### What this output is used for

It validates the separation:

```text
Capability = HOW
Binding    = WHERE
```

No new capability needs to be compiled merely because another compatible institution runs the same vendor application.

---

## Step 11 — validate the agent-facing capability interface

**Type:** Stretch

### Why this step exists

The optional capability API shows how an upstream AI agent could discover and invoke the saved automation like a normal typed tool.

### Command

```bash
python -m scripts.smoke_capability_api
```

### Expected result

You should see something equivalent to:

```text
DISCOVERED CAPABILITY:
('lookup_savings_balance', '1.0.0')

inputs:
['member_id']

outputs:
['current_savings_balance']

INVOCATION RESULT:
status: completed
checkpoint: True
evidence_run_id: replay_<id>
```

### What this output is used for

This proves the saved artifact can be exposed as an agent-invocable capability instead of requiring direct Python access to `ReplayEngine`.

It also generates evidence under:

```text
evidence/agent_api/
```

---

## Step 12 — validate production runtime policy

**Type:** Required-path validation

### Why this step exists

Policy must enforce deployment-level safety independently from the artifact.

### Command

```bash
python -m scripts.smoke_policy
```

### Expected result

The smoke demonstrates multiple policy cases:

```text
NORMAL REPLAY
    → completed

OUT-OF-SCOPE ROUTE
    → POLICY_URL_BLOCKED

RISKY LIVE TARGET
    → POLICY_HUMAN_REQUIRED

BLOCKED LIVE TARGET
    → POLICY_BLOCKED_PHRASE
```

You should also see checks such as:

```text
CONFIGURED ORIGIN/ROUTE ALLOWLIST   ✅
CONFIGURED ACTION ALLOWLIST         ✅
ACTUAL LIVE TARGET EVALUATED        ✅
RISKY ACTION → HUMAN_REQUIRED       ✅
BLOCKED ACTION → FAILED CLOSED      ✅
POST-ACTION URL CONTAINMENT         ✅
POLICY DECISIONS IN EVIDENCE        ✅
ZERO LLM POLICY DECISIONS           ✅
```

### What this output is used for

The run generates policy evidence under:

```text
evidence/policy/
```

That evidence is later selected into the final bundle.

---

## Step 13 — audit all evidence before final packaging

**Type:** Required path

### Why this step exists

By this point many source evidence runs may exist.

The final reviewer bundle should contain one strong, coherent proof for each required behavior rather than every development run.

### Command

```bash
python -m scripts.consolidate_evidence --audit-only
```

### Expected result

A complete project should show categories similar to:

```text
DISCOVERY              disc_<id> [gemini/gemini-2.5-flash]
REPLAY SUCCESS         replay_<id> [completed]
BUSINESS OUTCOME       replay_<id> [business_outcome]
RECOVERY               replay_<id> [completed]
HARD FAILURE           replay_<id> [failed]
HUMAN HANDOFF          replay_<id> [completed]
POLICY                 replay_<id> [human_required]
AGENT API (optional)   replay_<id> [completed]

ALL REQUIRED EVIDENCE FOUND ✅
```

### What this output is used for

`--audit-only` does not rebuild the final folder.

It answers:

> Do I already have all evidence needed for submission?

If anything is missing, rerun only the relevant smoke script.

---

## Step 14 — build the curated final evidence bundle

**Type:** Required path

### Why this step exists

The repository should include a reviewer-friendly `/evidence/` demonstration rather than requiring someone to search through all development runs.

### Command

```bash
python -m scripts.consolidate_evidence
```

### Expected result

You should see:

```text
ALL REQUIRED EVIDENCE FOUND ✅

FINAL EVIDENCE BUNDLE:
.../evidence/final

MISSING REQUIREMENTS: 0

SOURCE EVIDENCE LEFT UNCHANGED: ✅
CANONICAL ARTIFACT COPIED: ✅
REPLAY REDACTION AUDITED: ✅
MANIFEST GENERATED: ✅
BUNDLE CHECKSUMS GENERATED: ✅
```

### Files created

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

### What those outputs are used for

This folder is the **submission-facing proof package**.

`manifest.json` explains which source run was selected for each category.

`checksums.sha256` provides integrity checks for the curated bundle.

The original source evidence remains untouched.

---

## Step 15 — run the full automated regression suite

**Type:** Required final validation

### Why this step exists

The smoke scripts demonstrate end-to-end behavior. The test suite validates the individual contracts and failure cases.

### Command

```bash
python -m pytest -v
```

### Expected result

Current validated result:

```text
120 passed, 1 warning
```

The single warning is from the third-party `google-genai` package under Python 3.14 and is not a failing repository test.

### What this proves

The suite covers:

```text
typed models
LLM providers / normalization
discovery
compiler
surface behavior
locator ambiguity
deterministic replay
runtime classification
redaction
evidence
handoff
policy
tenancy
capability API
final evidence bundling
```

---

## Step 16 — optional: run the capability API as a real HTTP service

**Type:** Stretch

### Why this step exists

`smoke_capability_api` proves the service programmatically.

This step lets a reviewer interact with the capability through HTTP.

### Terminal 2 — capability API

```bash
CUA_ALLOW_DRAFT_CAPABILITIES=1 \
python -m uvicorn apps.capability_api:app \
  --host 127.0.0.1 \
  --port 8011
```

### Health check

```bash
curl http://127.0.0.1:8011/health
```

### Discover capabilities

```bash
curl http://127.0.0.1:8011/v1/capabilities
```

### Invoke the capability

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

### Expected result

The HTTP result should contain the same concepts as a direct replay:

```text
capability identity/version
status
outputs
checkpoint result
evidence run ID
```

### What this demonstrates

The capability is not just an internal Python object.

An upstream AI agent/service can:

```text
discover capability
      ↓
read typed input/output contract
      ↓
invoke exact version
      ↓
receive deterministic result
```

---

## Recommended reviewer demo order

If demonstrating the project live, I would not run every command above.

Use this sequence:

```text
1. Show LegacyCore briefly
2. Run smoke_compile with Gemini
3. Open the generated capability JSON
4. Run deterministic smoke_replay
5. Show one business/recovery/failure result from evidence
6. Run the manual smoke_handoff
7. Show policy smoke output
8. Open evidence/final
9. Finish with `pytest` result
```

That tells the full assignment story without spending time on internal validation scripts.

---

## How the outputs connect

The most important relationship in the repository is:

```text
┌─────────────────────────────┐
│ Genuine discovery evidence  │
│ disc_<id>                   │
└──────────────┬──────────────┘
               │ provenance
               ▼
┌─────────────────────────────┐
│ CapabilityArtifact          │
│ lookup_savings_balance      │
│ integrity_sha256            │
└──────────────┬──────────────┘
               │ deterministic input
               ▼
┌─────────────────────────────┐
│ Replay / policy / handoff   │
│ evidence runs               │
└──────────────┬──────────────┘
               │ curated by
               ▼
┌─────────────────────────────┐
│ evidence/final              │
│ reviewer-facing proof       │
└─────────────────────────────┘
```

So the outputs are not independent demo files:

- **discovery evidence** proves how the capability was learned,
- **the artifact** is the reusable product of that discovery,
- **replay evidence** proves that artifact executes deterministically,
- **handoff/policy evidence** proves safety behavior around replay,
- **the final bundle** ties the complete proof together.

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
