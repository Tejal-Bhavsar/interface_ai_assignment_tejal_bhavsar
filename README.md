Computer-Use Automation System

interface.ai Take-Home — End-to-End Computer-Use Automation for Legacy Applications

This repository implements a small but real version of the backend integration layer required to let AI agents operate applications that do not expose APIs.

The core idea is intentionally simple:

The model discovers. The artifact becomes a reusable capability. Deterministic replay is how the capability is invoked in production.

The implementation demonstrates that full thread against a synthetic banking application called LegacyCore X:

Natural-language goal
        |
        v
Genuine LLM discovery
observe -> decide -> act
        |
        v
Successful discovery result
        |
        v
Capability compiler
        |
        v
Typed + versioned + parameterized artifact
        |
        v
Deterministic ReplayEngine
(no LLM decisions)
        |
        +------------------------------+
        |              |               |
        v              v               v
     success      business outcome   recoverable
                                      / failure
                                         |
                                         v
                                  human intervention
                                  when required

The solution also adds production-oriented seams for configurable policy enforcement, redacted evidence, same-session human handoff, multi-tenant binding, and an optional agent-facing capability API.

All names, member IDs, balances, application errors, and account data in LegacyCore X are synthetic demonstration data.

1. Assignment coverage at a glance

Assignment requirement

Implementation

Main proof

Goal + target input

DiscoveryEngine.run(goal, entry_url)

Genuine discovery run

Real LLM observe -> decide -> act loop

cua/discovery.py + PlaywrightSurface + provider layer

evidence/final/01_discovery/

Real UI interaction

Playwright implementation of ComputerSurface

Discovery + replay evidence

Typed reusable artifact

CapabilityArtifact / compiler

capabilities/lookup_savings_balance.v1.json

Parameterized inputs

{{member_id}} compiler substitution

Saved artifact

Typed outputs

current_savings_balance

Saved artifact/API contract

Stable target identification

semantic/contextual locator candidates

Artifact + Playwright tests

Versioning / reviewability

capability id/version/schema/approval state

Saved artifact

Deterministic replay

ReplayEngine has no LLM decision dependency

replay evidence

Checkpoint verification

OUTPUT_EXISTS(current_savings_balance)

successful replay

Business outcome

MEMBER_NOT_FOUND

final evidence

Recoverable runtime condition

session/transient recovery rules

final evidence

Hard failure

permission/app-error handling

screenshot + sanitized HTML

Safety allowlists

PolicyEngine + config/policy.json

policy evidence

Risky/irreversible handling

human-required / blocked

policy tests/evidence

Sensitive-data redaction

typed sensitivity + evidence sanitization

redaction tests/final bundle

Structured observability

JSON/JSONL evidence

evidence/

Rich failure signal

masked screenshot + sanitized structure

failure evidence

Human escalation

InterventionRequest + ownership state machine

manual handoff evidence

Same live session takeover

same Playwright Page + BrowserContext

handoff smoke proof

Human actions recorded

browser event capture

handoff evidence

Multi-tenant design

TenantBindingRegistry

tenancy tests

Surface heterogeneity design

ComputerSurface abstraction

design/report

Optional agent-facing capability interface

FastAPI capability catalog + invoke endpoint

API smoke/evidence

Approval gate

draft capabilities blocked by default

catalog/replay tests

Final evidence bundle

audited, redacted, lineage-aware curation

evidence/final/

Test coverage

full pytest suite

120 passed

2. What was built

The system is a modular monolith. I intentionally did not split the take-home into distributed workers, queues, services, or orchestration infrastructure because those do not improve the correctness of the core vertical slice.

The main modules are:

apps/
├── server.py
│   Synthetic LegacyCore X target application
│
└── capability_api.py
    Agent-facing capability catalog/invocation API

capabilities/
└── lookup_savings_balance.v1.json
    Canonical reusable capability artifact

config/
├── llm.json
│   Provider/model configuration
├── app_profiles.json
│   Business outcome / recovery / failure semantics
├── policy.json
│   Deployment-level allowlists and risky/blocked phrases
└── tenant_bindings.json
    Tenant/application compatibility mappings

cua/
├── models.py
│   Core typed schemas
├── surface.py
│   Surface abstraction
├── playwright_surface.py
│   Browser implementation
├── discovery.py
│   LLM-driven discovery engine
├── discovery_evidence.py
│   Privacy-aware discovery evidence
├── compiler.py
│   Discovery -> capability compilation
├── replay.py
│   Deterministic production execution path
├── profiles.py
│   Application profile loader
├── policy.py
│   Runtime policy engine
├── redaction.py
│   Recursive sensitive-data redaction
├── evidence.py
│   Replay evidence recorder
├── handoff.py
│   Human intervention contracts/state
├── playwright_handoff.py
│   Same-session browser handoff
├── tenancy.py
│   Multi-tenant binding layer
├── capability_catalog.py
│   Versioned capability discovery
├── capability_service.py
│   Typed agent invocation service
├── evidence_bundle.py
│   Evidence audit/final curation
└── llm/
    Provider-agnostic LLM layer

scripts/
├── smoke_playwright.py
├── smoke_llm.py
├── smoke_discovery.py
├── smoke_compile.py
├── smoke_compile_offline.py
├── smoke_replay.py
├── smoke_replay_runtime.py
├── smoke_evidence.py
├── smoke_handoff.py
├── smoke_tenancy.py
├── smoke_capability_api.py
├── smoke_policy.py
└── consolidate_evidence.py

tests/
└── 120 automated tests across the implementation

evidence/
├── discovery/
├── replay/
├── policy/
├── agent_api/
└── final/

3. Concrete demo application: LegacyCore X

apps/server.py exposes a deliberately old-style synthetic banking application.

The UI is intentionally closer to enterprise back-office software than a polished consumer application:

server-rendered forms,

tables,

limited machine-friendly identifiers,

navigation between account pages,

runtime error screens,

transient states,

an exceptional security modal,

a risky "Open Sub-Account" flow.

The application is stable enough to make a record-once/replay-many architecture realistic, while still containing the kinds of runtime conditions that matter in production.

Synthetic cases include:

Input

Behavior

normal known member

happy-path checking/savings navigation

unknown member

business outcome: MEMBER_NOT_FOUND

recovery member

first request exposes session expiry, deterministic reload succeeds

transient-busy member

first request exposes busy state, deterministic reload succeeds

permission-denied input

hard failure

application-error input

hard failure

security-challenge member

requires same-session human acknowledgement

open-sub-account page

risky/blocked policy demonstrations

4. Architecture

4.1 Surface boundary

ComputerSurface defines the automation contract independently from Playwright.

Conceptually it exposes operations for:

start / close
navigate / reload
observe
resolve target
fill / click / select
extract
assert / wait
capture screenshot
capture structural snapshot

PlaywrightSurface is only one implementation.

This matters because the target environment may eventually include:

modern web
legacy web
frames / nested tables
remote desktop
native desktop
accessibility-tree automation
image/coordinate automation

The discovery/compiler/replay contracts should not have to change just because the physical interaction backend changes.

4.2 Discovery boundary

DiscoveryEngine is the only place where a model is allowed to decide what to do next.

It receives:

goal
entry URL
surface
LLM provider
policy
step limit

and repeatedly performs:

OBSERVE live state
       ↓
ASK LLM for one typed action
       ↓
RESOLVE proposed live target
       ↓
CHECK policy
       ↓
ACT
       ↓
OBSERVE again

Stopping conditions include:

goal completed,

model requests human intervention,

policy blocks/requires human,

target cannot be uniquely resolved,

action fails,

success condition fails,

maximum step count.

4.3 Compilation boundary

Discovery is exploratory; production replay should not be.

The compiler therefore does not save the raw model transcript as automation.

Instead it converts a successful discovery result into a smaller production contract:

discovery result
      ↓
remove discovery-only COMPLETE action
      ↓
parameterize concrete invocation values
      ↓
canonicalize targets
      ↓
attach typed inputs / outputs
      ↓
attach application runtime semantics
      ↓
attach checkpoint
      ↓
attach safety metadata
      ↓
attach discovery provenance
      ↓
validate no sensitive runtime leakage
      ↓
compute integrity SHA-256
      ↓
CapabilityArtifact

4.4 Replay boundary

ReplayEngine intentionally contains no model-decision dependency.

Its inputs are:

saved artifact
typed runtime inputs
tenant/deployment entry URL
surface
policy
optional evidence recorder
optional human-handoff handler

The replay engine follows only the saved contract.

4.5 Policy boundary

Capability safety answers:

What was this capability reviewed/designed to do?

Runtime policy answers:

What is this deployment allowed to do right now?

Both must allow execution.

4.6 Evidence boundary

Evidence recording is passive.

It records what happened but never decides what should happen next.

This keeps observability from becoming part of the control plane.

5. Setup

5.1 Prerequisites

Recommended:

Python 3.11+
Playwright Chromium

The final project was validated locally on Python 3.14.4.

5.2 Create a virtual environment

python -m venv .venv
source .venv/bin/activate

5.3 Install Python dependencies

python -m pip install -r requirements.txt

5.4 Install Chromium for Playwright

python -m playwright install chromium

6. Configuration

Configuration is intentionally kept outside the automation code.

6.1 config/llm.json

Controls available model providers and models.

Implemented adapters include:

mock
OpenAI
Anthropic
Gemini
Grok
Ollama
OpenAI-compatible endpoints

Select a provider with:

export CUA_LLM_PROVIDER=gemini

For a live provider, also export the API-key environment variable named by that provider's api_key_env field in config/llm.json.

The final genuine discovery proof in this repository uses:

provider: gemini
model: gemini-2.5-flash

6.2 config/app_profiles.json

Contains reusable application-runtime semantics.

For LegacyCore, rules classify states such as:

MEMBER_NOT_FOUND
SESSION_EXPIRED
TRANSIENT_BUSY
PERMISSION_DENIED
APPLICATION_ERROR
SECURITY_VERIFICATION

Rules are compiled into the capability so replay understands expected application behavior without asking a model.

6.3 config/policy.json

The global runtime policy contains:

allowed origins
allowed route prefixes
allowed action types
risky phrases
blocked phrases
risky action mode

Important design choice:

Policy checks the actual resolved live element metadata, not only an LLM/artifact description.

This prevents a benign target description from hiding a dangerous live button.

6.4 config/tenant_bindings.json

Tenant bindings separate reusable logic from deployment configuration.

The artifact says:

HOW to look up the savings balance

The binding says:

WHERE this artifact may run
WHICH vendor/version it is compatible with
WHICH artifact versions are approved

7. Exact end-to-end demo path

This is the shortest reviewer path through the assignment.

Terminal 1 — run LegacyCore X

source .venv/bin/activate

python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000

Target:

http://127.0.0.1:8000/legacy

Terminal 2 — genuine LLM discovery + compilation

Configure a live provider.

Example:

source .venv/bin/activate

export CUA_LLM_PROVIDER=gemini

python -m scripts.smoke_compile

This command performs:

natural-language goal
       ↓
real browser observation
       ↓
Gemini decision
       ↓
live target resolution
       ↓
policy evaluation
       ↓
browser action
       ↓
repeat until complete
       ↓
persist redacted discovery evidence
       ↓
compile capability
       ↓
verify no concrete runtime data leaked
       ↓
compute artifact integrity SHA
       ↓
save capability

Successful output creates:

capabilities/lookup_savings_balance.v1.json

and:

evidence/discovery/disc_<run-id>/

Terminal 2 — deterministic replay

Keep LegacyCore running.

python -m scripts.smoke_replay

This executes the resulting artifact without LLM decisions.

8. Genuine discovery proof

The final canonical discovery included in the evidence bundle is:

run_id:   disc_22b2281984ae
provider: gemini
model:    gemini-2.5-flash
status:   completed

The model discovered this flow against the live browser:

1. FILL Member ID textbox
2. CLICK Search
3. CLICK Savings
4. EXTRACT Current Balance using same-row contextual targeting
5. COMPLETE

The discovered reusable operations were compiled to four capability steps because COMPLETE is a discovery control-flow action, not a production browser operation.

The canonical compiled artifact has:

capability id: lookup_savings_balance
version:       1.0.0
schema:        1.0
approval:      draft
input:         member_id
output:        current_savings_balance
steps:         4

Artifact integrity SHA-256:

cd2a9e2e522df917c914b5e1d1eb1f312ed171268f95b2dce8f976b82f50a6f5

9. Goal-driven discovery loop

The LLM provider returns a typed AgentAction, not arbitrary executable code.

Supported action semantics include:

NAVIGATE
CLICK
FILL
SELECT
EXTRACT
WAIT
ASSERT
COMPLETE
REQUEST_HUMAN

A proposed action can contain:

action type
reason
target descriptor
value
output name
success condition
risk hint

Before an action executes:

the target is resolved against the live surface,

ambiguity is rejected,

current URL is policy-checked,

the actual resolved target is policy-checked,

an explicit destination URL is checked when known,

only then is the action executed.

This avoids treating model output as trusted automation.

10. Locator and target strategy

A TargetDescriptor contains an ordered set of LocatorCandidates.

Supported kinds include:

ROLE
LABEL
TEXT
PLACEHOLDER
RELATIVE_TEXT
CSS
XPATH

The implementation prefers semantic/contextual strategies.

Examples from the saved capability:

Member ID textbox:
role=textbox + accessible name "Member ID"

Search:
role=button + name "Search"

Savings:
role=link + name "Savings"

Balance:
reference text "Current Balance"
relation same_row

The final extraction does not locate the concrete discovered balance value.

That value changes per member and therefore would be a brittle locator.

Ambiguity handling

The resolver does not use .first() as a silent escape hatch.

A candidate must resolve uniquely.

If multiple controls match, the action fails closed.

Fallback order

A target may contain multiple locator candidates.

Replay attempts them in declared order, but each candidate still has to satisfy uniqueness.

11. Capability artifact design

The artifact is a production contract, not an execution transcript.

Major fields include:

schema_version

identity
  id
  name
  version
  description
  approval_state

target

inputs
outputs

steps

business_outcomes
recoveries
failures

checkpoint
safety

discovery
  run_id
  provider
  model
  source tenant
  source goal template

integrity_sha256

Typed inputs

Example:

member_id: string, sensitive

The concrete discovery value is parameterized:

1001
  ↓
{{member_id}}

Typed outputs

Example:

current_savings_balance: string, sensitive

The actual discovery balance is not stored in the reusable artifact.

Ordered steps

Each production step contains:

step id
description
action
target
runtime value/template
output name
preconditions
postconditions
risk level

Checkpoint

The example capability uses:

OUTPUT_EXISTS(current_savings_balance)

Replay is not successful merely because all clicks completed; the declared capability outcome must exist.

Provenance

The artifact keeps the discovery run/provider/model so a reviewer can connect the saved automation to the real discovery evidence.

Integrity

The compiler computes a SHA-256 over canonical artifact content.

Replay verifies integrity before execution.

12. Compiler safety decisions

The compiler fails closed when the discovery cannot be converted safely.

Examples include:

discovery did not complete
no reusable steps
declared input was never used
dynamic extracted runtime text is being turned into a locator
expected output contract changed
sensitive discovery values would remain in the artifact
artifact integrity cannot be validated

This is a deliberate separation of concerns:

LLM discovery may be flexible
        |
        v
compiler is strict
        |
        v
replay receives only reviewed structure

13. Deterministic replay

Replay does not re-ask the model how to perform the task.

Conceptually:

load artifact
    ↓
verify integrity
    ↓
enforce approval state
    ↓
validate input names/types
    ↓
bind {{placeholders}}
    ↓
validate artifact-level action safety
    ↓
check runtime policy
    ↓
resolve target deterministically
    ↓
execute action
    ↓
classify runtime state
    ↓
bounded recovery / outcome / failure / human
    ↓
verify checkpoint
    ↓
return typed result

Draft behavior

The saved demonstration capability is intentionally still draft.

By default:

draft capability -> not callable

Smoke scripts can explicitly opt in to demonstrate the vertical slice.

This gives the schema a real approval seam instead of claiming every generated artifact is production-approved.

14. Replay result contract and error taxonomy

Caller-visible statuses are:

COMPLETED
BUSINESS_OUTCOME
FAILED
HUMAN_REQUIRED

Runtime states are classified as:

NORMAL
BUSINESS_OUTCOME
RECOVERABLE
HARD_FAILURE
HUMAN_REQUIRED

This prevents all non-happy-path situations from collapsing into a generic exception.

Business outcome

Example:

MEMBER_NOT_FOUND

A nonexistent member is a legitimate result the caller needs to know, not a system crash.

Recoverable conditions

Examples:

SESSION_EXPIRED
TRANSIENT_BUSY

Recovery is deterministic and bounded.

For the synthetic application, the configured strategy is reload with a maximum attempt count.

Replay never retries forever.

Hard failures

Examples:

PERMISSION_DENIED
APPLICATION_ERROR

Replay stops and surfaces a structured failure including the failed step and runtime state.

Human-required state

Example:

SECURITY_VERIFICATION

This routes into the human intervention mechanism.

15. Runtime classification precedence

The classifier is deliberately fail-closed.

Conceptually:

failure / human-required
        ↓
recoverable
        ↓
business outcome
        ↓
normal

A known severe state must not accidentally be hidden by a lower-priority match.

16. Safety and policy guardrails

Safety is layered.

Layer 1 — artifact safety contract

The artifact declares which actions and risk levels belong to the reviewed capability.

Replay cannot simply ignore this contract.

Layer 2 — deployment policy

PolicyEngine independently evaluates:

current URL
destination URL
action allowlist
target description
actual resolved element metadata
risk level
configured blocked phrases
configured risky phrases
post-action URL

URL containment

Origins are matched exactly.

Route prefixes use path-boundary logic.

Therefore:

/legacy/member/1001    allowed
/legacyevil            blocked
/legacy-evil           blocked

when /legacy is the configured route prefix.

Live-target enforcement

Policy evaluates metadata from the element actually found in the live browser, including available:

tag
role
text
accessible name
aria label
placeholder
href

This protects against a case such as:

description from artifact/model:
"Continue"

actual live button:
"Confirm Open Sub-Account"

The live blocked operation wins.

Risk handling

Current behavior is conservative:

SAFE              -> may execute if otherwise allowed
RISKY             -> HUMAN_REQUIRED (configurable mode)
IRREVERSIBLE      -> BLOCK
blocked phrase    -> BLOCK

Blocked phrases take precedence over generic risky handling.

Post-action containment

After browser actions/recovery navigation, the resulting live URL is checked again.

This protects against unexpected redirects.

17. Sensitive-data handling

This is a financial-domain system, so evidence is designed around the assumption that UI state can contain regulated data.

Typed sensitivity

Inputs and outputs can be explicitly marked sensitive.

Example:

member_id                  sensitive
current_savings_balance    sensitive

Artifact protection

Concrete discovery-time inputs and outputs are rejected from the reusable artifact.

Replay evidence

Replay evidence redacts:

sensitive input values
sensitive output values
known runtime secrets
sensitive member IDs embedded in URLs
sensitive query parameters

Screenshots

The browser surface masks:

[data-sensitive=true]

before failure screenshots are persisted.

Structural snapshots

HTML/structure evidence is sanitized rather than stored verbatim.

Discovery evidence

Discovery evidence intentionally does not persist raw visible page text or raw LLM responses.

It persists safer proof signals such as:

provider + model
observation URL/title after sanitization
control summaries without input values
control count
visible-text character count
ARIA-snapshot character count
observation SHA-256 fingerprint
LLM-decided typed action
resolved live target metadata
policy evaluation
action execution
final status

FILL values and extracted outputs are redacted.

This provides evidence that discovery really occurred without turning the evidence directory into a store of raw financial UI content.

18. Evidence and observability

Replay run layout:

evidence/replay/replay_<id>/
├── metadata.json
├── artifact.json
├── events.jsonl
├── result.json
├── failure_<step>.png      # when applicable
└── failure_<step>.html     # when applicable

Discovery run layout:

evidence/discovery/disc_<id>/
├── metadata.json
├── events.jsonl
└── result.json

The structured event stream records enough information to answer:

what happened?
which step?
why?
what policy decision was made?
was recovery attempted?
did a human take control?
what was the terminal result?

Failure screenshot/structure evidence gives a richer debugging signal than JSON alone.

19. Human-in-the-loop escalation and same-session handoff

The human handoff implementation is not a placeholder.

The demonstrated runtime case is:

lookup member
      ↓
open Savings
      ↓
LegacyCore security modal
      ↓
SECURITY_VERIFICATION detected
      ↓
automation pauses
      ↓
InterventionRequest
      ↓
ownership = HUMAN
      ↓
human acts in SAME browser
      ↓
human requests resume
      ↓
automation validates live state
      ↓
ownership = AUTOMATION
      ↓
replay continues

Intervention context

The request includes enough information for the operator to understand the stop:

intervention ID
capability
step
reason
message
live URL
resume attempt

Same live session

The handoff preserves the exact:

Playwright Page
BrowserContext

The operator is instructed to use the already-open browser rather than opening a new one.

Human action capture

Browser interaction capture records sanitized human actions across the handoff.

The final manual proof recorded:

click: Acknowledge & Continue

Resume is validated

Pressing Enter is only:

REQUEST RESUME

not:

AUTOMATICALLY GIVE CONTROL BACK

Before replay resumes, automation validates:

current URL is still allowed
blocking state is gone
runtime state is acceptable
next preconditions are valid
next target can resolve uniquely

Resume attempts are bounded.

20. Handoff limitation

There are currently two escalation sources:

runtime HUMAN_REQUIRED
policy HUMAN_REQUIRED

The real same-session handoff path is fully implemented for runtime application states such as SECURITY_VERIFICATION.

A policy-produced HUMAN_REQUIRED currently returns a structured terminal replay result before the risky action instead of automatically entering the persistent same-session API handoff flow.

This is documented intentionally rather than hidden.

A production next step would route both sources through one intervention/ownership service.

21. Multi-tenant design

The same automation logic should not be rebuilt separately for every institution using the same vendor application.

The design therefore separates:

Capability = HOW
Binding    = WHERE

Example conceptual binding:

tenant: northstar-cu
application: member-servicing
vendor product: legacycore-x
compatibility: legacycore-x:v1
entry URL: tenant-specific
allowed capability versions: [...]

The tenancy tests prove:

same artifact -> two compatible tenant bindings
unknown tenant -> fail closed
incompatible vendor/version -> fail closed
binding -> does not mutate artifact

A tenant running an incompatible future application version is rejected rather than optimistically reusing the automation.

22. Heterogeneous surface design

Only a browser surface is implemented because this is a focused vertical slice.

The abstraction is intentionally broader.

A future desktop surface could map the same concepts:

Capability concept

Web implementation

Desktop/remote equivalent

observe

DOM/accessibility snapshot

accessibility tree/screenshot

role locator

ARIA role

accessibility role/control type

label

form label

accessibility name

relative text

table/DOM relationship

visual/accessibility relationship

click

Playwright click

OS/accessibility click

fill

Playwright fill

keyboard/accessibility value

screenshot

page screenshot

desktop capture

structure snapshot

sanitized HTML

accessibility-tree snapshot

The artifact remains semantic; only the surface resolver/executor changes.

23. Agent-facing capability interface — stretch goal

The repository implements one optional stretch goal deeply: an agent-facing capability interface.

apps/capability_api.py exposes a small FastAPI catalog.

Endpoints include:

GET  /health
GET  /v1/capabilities
GET  /v1/capabilities/{capability_id}?version=...
POST /v1/capabilities/{capability_id}/invoke

A calling agent supplies:

capability version
tenant ID
application key
typed arguments

The service performs:

catalog lookup
exact version lookup
approval validation
tenant/application binding
compatibility validation
deterministic replay
evidence creation
structured result

Start the API

LegacyCore:

python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000

Capability API:

CUA_ALLOW_DRAFT_CAPABILITIES=1 \
python -m uvicorn apps.capability_api:app \
  --host 127.0.0.1 \
  --port 8011

Discover capabilities

curl http://127.0.0.1:8011/v1/capabilities

Invoke the capability

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

A smoke script exercises the same path:

python -m scripts.smoke_capability_api

24. Approval seam

The artifact schema contains:

draft
approved

The final demonstration artifact is intentionally draft.

The catalog can expose it for inspection, but unattended invocation is disabled by default.

The smoke environment explicitly enables draft execution:

CUA_ALLOW_DRAFT_CAPABILITIES=1

This is a narrow implementation of the assignment's confidence/approval direction without pretending to implement a full approval service.

25. Running without a live model service

A live model is required only to create a new genuine discovery run.

The saved capability can be replayed without a live LLM.

Start LegacyCore:

python -m uvicorn apps.server:app \
  --host 127.0.0.1 \
  --port 8000

Then:

python -m scripts.smoke_replay

The provider abstraction can also be tested locally with:

CUA_LLM_PROVIDER=mock \
python -m scripts.smoke_llm

Most automated tests use mocks/fakes and do not need external model access.

26. Useful demo commands

Surface

python -m scripts.smoke_playwright

LLM provider contract

CUA_LLM_PROVIDER=mock \
python -m scripts.smoke_llm

Genuine discovery only

CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_discovery

Genuine discovery + compile

CUA_LLM_PROVIDER=gemini \
python -m scripts.smoke_compile

Deterministic replay

python -m scripts.smoke_replay

Runtime taxonomy

python -m scripts.smoke_replay_runtime

Evidence

python -m scripts.smoke_evidence

Real manual handoff

python -m scripts.smoke_handoff

Scripted regression handoff

python -m scripts.smoke_handoff --auto

The --auto version is test/regression support; it is not the final human proof.

Multi-tenant binding

python -m scripts.smoke_tenancy

Agent-facing capability API

python -m scripts.smoke_capability_api

Runtime policy

python -m scripts.smoke_policy

Final evidence audit

python -m scripts.consolidate_evidence --audit-only

Build curated final evidence

python -m scripts.consolidate_evidence

27. Final evidence bundle

The reviewer-facing bundle is:

evidence/final/
├── README.md
├── manifest.json
├── checksums.sha256
│
├── 01_discovery/
├── 02_artifact/
├── 03_replay_success/
├── 04_business_outcome/
├── 05_recovery/
├── 06_hard_failure/
├── 07_human_handoff/
├── 08_policy/
└── 09_agent_api/

The final selected proof is:

Category

Selected run

Genuine discovery

disc_22b2281984ae

Successful replay

replay_b5da39f38b05

Business outcome

replay_4647a6ff59f6

Recoverable replay

replay_b4775e61a9d5

Hard failure

replay_530635599c3d

Real manual handoff

replay_2d8ca6b9db94

Runtime policy

replay_7999ad388fd5

Agent API

replay_acf52073349e

The evidence bundler is deliberately non-destructive.

It:

finds the canonical discovery evidence
requires a genuine non-mock provider
selects replay evidence tied to the canonical artifact lineage
requires a real manual handoff rather than scripted regression
audits sensitive replay fields
copies only curated proof
generates manifest.json
generates SHA-256 checksums
leaves source evidence untouched

28. Final genuine discovery evidence

The final discovery evidence includes actual events such as:

discovery_started
policy_evaluated
observation
llm_decision
target_resolved
action_executed
...
discovery_finished

It proves a genuine model was in the discovery loop while avoiding persistence of raw financial UI text.

29. Test suite

Run everything:

python -m pytest -v

Final validation:

120 passed, 1 warning

The single warning is a third-party google-genai deprecation warning observed under Python 3.14 and does not represent a failing project test.

The suite covers:

capability catalog/API
compiler safety
discovery
discovery evidence
replay evidence
final evidence bundling
human handoff
LLM normalization/providers
typed models
Playwright surface
policy unit behavior
policy/replay integration
application profiles
redaction
replay taxonomy
surface abstraction
multi-tenant binding

30. Important design decisions and trade-offs

LLM in discovery, not replay

Decision: use model reasoning only to learn the task.

Why: replay should be reliable, cheap, auditable, and predictable.

Trade-off: replay does not automatically reason around unknown UI drift.

Artifact, not transcript

Decision: compile a typed capability rather than replaying the model conversation.

Why: exploration history and concrete runtime values are not a production contract.

Trade-off: compiler design is more work but gives a much cleaner system boundary.

Semantic targets over brittle selectors

Decision: prefer role/label/text/context and reject ambiguity.

Why: generated CSS/XPath can be fragile and accidental.

Trade-off: some truly hostile surfaces will require image/accessibility/coordinate strategies.

Embedded runtime semantics

Decision: business/recovery/failure rules are part of the reusable application capability.

Why: these are application semantics replay must understand deterministically.

Trade-off: when vendor behavior changes materially, the capability/profile must be versioned.

Global policy outside the artifact

Decision: deployment policy is separate from artifact safety.

Why: institution-level restrictions can change independently of automation logic.

Fail closed

Decision: ambiguous target, bad input, incompatible tenant, integrity failure, unsafe action, or blocked navigation stops execution.

Why: a financial automation system should not guess when the safety contract is unclear.

Modular monolith

Decision: one process/codebase with explicit interfaces.

Why: the assignment evaluates judgment and a complete core flow, not distributed infrastructure.

31. What was deliberately not built

The following are deliberate cuts, not hidden TODOs:

native desktop ComputerSurface
VNC/co-browsing operator product UI
distributed automation workers
queue/cluster orchestration
persistent database-backed capability registry
RBAC/SSO
secret-manager integration
full human approval product
confidence scoring based on many production replays
automatic LLM repair during deterministic replay
large-scale drift telemetry
cross-tenant override language
multi-run flakiness scoring
code-generation stretch goal

The architecture leaves seams for these without implementing them prematurely.

32. What I would build next

Priority order:

1. Unify policy HUMAN_REQUIRED with persistent same-session handoff
2. Persistent capability/version/approval registry
3. Second non-DOM ComputerSurface
4. Tenant/vendor drift and compatibility telemetry
5. Reviewed re-discovery/versioning workflow
6. Multi-run reliability/confidence metrics
7. Operator-facing intervention queue/UI

I would not make open-ended LLM recovery the default replay behavior.

If a reviewed capability becomes unsafe or ambiguous, stopping and creating a reviewed new version is preferable to silently re-introducing model reasoning into production execution.

33. Submission checklist

Before submitting:

[ ] README.md exists at repo root
[ ] REPORT.md exists at repo root
[ ] capability artifact committed
[ ] genuine discovery evidence committed
[ ] deterministic replay evidence committed
[ ] exceptional replay evidence committed
[ ] manual same-session handoff evidence committed
[ ] policy evidence committed
[ ] evidence/final manifest and checksums committed
[ ] no API keys/secrets committed
[ ] pytest is green
[ ] exact demo commands work from a fresh shell
[ ] GitHub repository is public

Current validated project state:

genuine discovery             ✅
typed capability              ✅
deterministic replay          ✅
checkpoint                    ✅
business outcome              ✅
bounded recovery              ✅
hard failure evidence         ✅
same-session human handoff    ✅
runtime policy                ✅
redaction                     ✅
multi-tenant design           ✅
agent capability API          ✅
final evidence bundle         ✅
120 tests passing             ✅

For the architectural reasoning and trade-offs, see REPORT.md.