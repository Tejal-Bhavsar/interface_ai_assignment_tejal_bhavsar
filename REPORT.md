# Architecture

> **Core production split:** the LLM discovers the task once; a structured capability captures what was learned; deterministic replay invokes that capability later without an LLM decision loop.

The implementation is a **modular monolith**. I chose this intentionally: the hard part of this assignment is the correctness of the control boundaries—not queues, clusters, or distributed orchestration.

```text
Goal + Entry URL
      │
      ▼
DiscoveryEngine ──► LLM ActionProvider
      │
      ▼
ComputerSurface
      │
      ▼
CapabilityCompiler
      │
      ▼
CapabilityArtifact
      │
      ▼
ReplayEngine
      │
      ├──► PolicyEngine
      ├──► EvidenceRecorder
      └──► Human Handoff
```

**Key boundaries**

| Boundary | Responsibility |
|---|---|
| `ComputerSurface` | UI interaction abstraction |
| `PlaywrightSurface` | Browser implementation |
| `DiscoveryEngine` | Genuine observe → decide → act loop |
| `CapabilityCompiler` | Converts successful discovery into reusable automation |
| `ReplayEngine` | Executes saved capability deterministically |
| `PolicyEngine` | Deployment-level safety enforcement |
| Evidence recorders | Persist what happened without affecting control flow |

`DiscoveryEngine` is the only component that uses a model to choose the next action. Each iteration observes the live state, requests one typed `AgentAction`, resolves the proposed target against the actual UI, evaluates policy, executes the action, and observes again.

The final live proof used **Gemini 2.5 Flash** and produced discovery run `disc_22b2281984ae`. Discovery evidence records safe observation fingerprints/control summaries, LLM decisions, resolved targets, policy results, browser actions, and the terminal result.

The provider abstraction also contains implemented adapters for OpenAI, Anthropic, Grok/xAI, Ollama, and OpenAI-compatible endpoints. Their request/response contracts are covered by provider/unit tests, but I did not run a separate paid end-to-end discovery against every provider because of API-budget constraints. I therefore claim **full live validation only for Gemini 2.5 Flash**, not provider parity across every external service.

A separate compiler is a deliberate design decision. I did **not** make the raw model transcript the production automation because transcripts contain exploration, concrete values, and model reasoning. The compiler instead creates a smaller contract with parameterized inputs, typed outputs, stable target descriptors, runtime semantics, checkpoint, safety metadata, provenance, and integrity verification.

`ReplayEngine` is the production execution path and intentionally has **no LLM decision dependency**. The optional FastAPI capability interface demonstrates how an upstream AI agent could discover and invoke an exact capability version with typed arguments while still executing the same deterministic replay path.

**Trade-off:** this design gives strong auditability and predictability, but unknown UI drift is not automatically “reasoned around” during replay. I prefer stopping safely and producing evidence over silently reintroducing model reasoning.

---

# Artifact schema

> **The artifact is a capability contract, not a macro and not a transcript.**

The core `CapabilityArtifact` contains:

```text
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
discovery provenance
integrity_sha256
```

The schema is designed so both a human reviewer and a calling agent can answer:

- What does this capability do?
- What inputs does it require?
- What outputs does it return?
- What actions will it take?
- How are UI controls identified?
- What counts as success?
- What runtime outcomes/recoveries/failures are understood?
- What safety limits apply?
- Which discovery run produced it?

### Parameterization

The discovery run uses a concrete member ID, but the compiler converts it into:

```text
1001
  ↓
{{member_id}}
```

The artifact therefore contains the reusable input contract instead of one person's data. Concrete runtime outputs such as the discovered savings balance are also excluded.

### Target representation

Each executable step stores an action and an optional `TargetDescriptor` containing ordered locator candidates.

The browser implementation supports role/name, label, text, placeholder, relative text, CSS, and XPath. The preferred strategies are semantic/contextual.

Example:

```text
Current Balance
      +
relation = same_row
      ↓
extract balance value
```

This is more reusable than recording the literal discovered balance.

Resolution must be unique. Ambiguous matches are rejected instead of silently using `.first()`.

### Runtime semantics

Business outcomes, recoveries, and failures are embedded in the capability because they are application semantics required by deterministic replay.

Examples:

| Runtime state | Meaning |
|---|---|
| `MEMBER_NOT_FOUND` | expected business outcome |
| `SESSION_EXPIRED` | recoverable |
| `TRANSIENT_BUSY` | recoverable |
| `PERMISSION_DENIED` | hard failure |
| `APPLICATION_ERROR` | hard failure |
| `SECURITY_VERIFICATION` | human required |

Tenant entry URLs remain outside the artifact so the same capability can bind to multiple compatible institutions without mutation.

The final example capability is:

```text
id:             lookup_savings_balance
version:        1.0.0
schema:         1.0
approval:       draft
input:          member_id
output:         current_savings_balance
steps:          4
checkpoint:     OUTPUT_EXISTS(current_savings_balance)
```

Integrity SHA-256:

```text
cd2a9e2e522df917c914b5e1d1eb1f312ed171268f95b2dce8f976b82f50a6f5
```

Draft capabilities are not callable by default; demo execution must explicitly opt in.

---

# Determinism & error handling

> **Replay follows the artifact. It does not ask a model what to do next.**

The replay path is:

```text
load artifact
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
check deployment policy
    ↓
resolve target uniquely
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

Before execution, replay rejects:

- invalid artifact integrity,
- draft capabilities unless explicitly enabled,
- missing inputs,
- unknown inputs,
- incorrectly typed inputs,
- actions outside the artifact safety contract,
- policy-disallowed navigation/actions.

Target resolution is deterministic and fail-closed. Locator candidates are attempted in declared order, but every candidate must uniquely identify a control. The engine does not guess when the UI is ambiguous.

Navigation is also contained at multiple points:

1. entry URL checked before navigation,
2. known destination checked before execution,
3. actual browser URL checked after the action/recovery.

### Result taxonomy

Caller-visible result:

```text
completed
business_outcome
failed
human_required
```

Internal runtime classification:

```text
normal
business_outcome
recoverable
hard_failure
human_required
```

The distinction matters. For example, a nonexistent member is a legitimate domain result rather than an automation crash.

Recovery is deterministic and bounded. Known session-expired/transient-busy states can trigger reload and reclassification, but every rule has `max_attempts`; replay cannot retry forever.

Hard failures such as permission denial or application error stop with a structured result containing the failed step and runtime state.

Finally, a replay is not successful only because its click sequence finished. The declared checkpoint must pass and declared outputs must exist.

On failure, evidence includes structured JSON/JSONL plus a richer masked screenshot and sanitized HTML/structure signal.

**Deliberate cut:** I did not implement LLM self-healing during replay. If the capability no longer resolves safely, the system stops and produces evidence for review/re-discovery.

---

# Heterogeneity & multi-tenant

> **The design separates surface, capability, and deployment.**

### Surface heterogeneity

`ComputerSurface` defines the interaction contract used by discovery and replay:

```text
observe
resolve
navigate / reload
click / fill / select
extract
check conditions
capture evidence
```

`PlaywrightSurface` maps those concepts to a browser.

A future desktop/remote implementation could map the same semantic operations differently:

| Capability concept | Browser | Desktop / remote |
|---|---|---|
| observe | DOM/accessibility snapshot | accessibility tree / screenshot |
| role/name | ARIA role/name | accessibility role/name |
| relative text | DOM/table relation | visual/accessibility relation |
| click | Playwright click | OS/accessibility click |
| fill | Playwright fill | keyboard/accessibility value |
| screenshot | page screenshot | desktop capture |
| structure evidence | sanitized HTML | accessibility-tree snapshot |

The artifact stays semantic; only the surface resolver/executor changes.

### Multi-tenant reuse

I separate:

```text
Capability = HOW
Binding    = WHERE
```

A `TenantApplicationBinding` carries:

- tenant/application identity,
- entry URL,
- vendor product,
- compatibility key,
- enabled state,
- allowed capability versions.

The same artifact can bind to two compatible institutions without mutation. Unknown tenants and incompatible vendor/application versions fail closed.

A future `legacycore-x:v2` deployment is intentionally considered incompatible with the current v1 capability until explicitly reviewed.

**Scale path:** at larger scale I would add a persistent vendor/product/version registry plus compatibility and drift telemetry. I deliberately did not build queues, distributed workers, clusters, or fleet orchestration because they do not improve the correctness of this vertical slice.

---

# Escalation & handoff

> **Human handoff is a real control-transfer mechanism, not a TODO.**

The demonstrated case is LegacyCore's `SECURITY_VERIFICATION` modal.

```text
AUTOMATION
    ↓
WAITING_FOR_HUMAN
    ↓
HUMAN
    ↓
VALIDATING_RESUME
    ↓
AUTOMATION
```

When the runtime classifier detects the condition, replay creates an `InterventionRequest` carrying:

- intervention ID,
- capability,
- current step,
- reason,
- message,
- live URL,
- resume attempt.

`PlaywrightHumanHandoff` keeps the exact existing `Page` and `BrowserContext`. The operator works in the already-open browser rather than recreating the session.

Browser instrumentation records sanitized human actions. The final manual evidence captured:

```text
click: Acknowledge & Continue
```

### Resume validation

A human saying “resume” does **not** automatically return control.

Before automation resumes, the system validates:

```text
current URL is still allowed
blocking condition is gone
runtime state is acceptable
next-step conditions hold
next target resolves uniquely
```

Resume attempts are bounded. Failed validation leaves ownership with the human instead of continuing blindly.

The curated evidence bundle contains a **real manual same-session handoff**. A scripted `--auto` mode exists only for unattended regression.

### Known integration cut

Application-runtime `HUMAN_REQUIRED` is connected to the same-session handoff mechanism.

A policy-generated `HUMAN_REQUIRED` currently stops with a structured terminal result before the risky action instead of automatically entering the persistent handoff flow.

The next production step would unify both sources behind one durable intervention/session service.

---

# Safety

> **Safety is enforced twice: by the capability contract and by deployment policy.**

### Artifact-level safety

The capability's `SafetyContract` defines the action/risk envelope the capability was designed for.

### Deployment-level safety

`PolicyEngine` loads `config/policy.json`, including:

```text
allowed origins
allowed route prefixes
allowed action types
risky phrases
blocked phrases
risky-action mode
```

Replay cannot bypass artifact safety just because deployment policy allows an action, and it cannot bypass deployment policy just because the artifact contains the action.

### Live target evaluation

Policy evaluates the **actual resolved control**, not only its stored/model-generated description.

Example:

```text
description:
"Continue"

live button:
"Confirm Open Sub-Account"
```

The live target metadata wins.

Current behavior:

| Risk | Behavior |
|---|---|
| safe | execute if otherwise allowed |
| risky | require human |
| irreversible | block |
| blocked phrase | block |

Blocked phrases take precedence over generic risky handling.

### Navigation safety

Allowed route-prefix matching uses path boundaries.

So an allowlist for:

```text
/legacy
```

does not accidentally permit:

```text
/legacy-evil
```

Destination and post-action URLs are also checked as defense in depth.

### Sensitive-data handling

Typed fields can be marked sensitive. The compiler prevents concrete discovery inputs and outputs from being embedded in the reusable artifact.

Replay evidence redacts:

- sensitive inputs,
- sensitive outputs,
- known runtime values,
- member IDs inside URLs,
- sensitive query parameters.

Failure screenshots mask:

```css
[data-sensitive=true]
```

Structural HTML is sanitized.

Discovery evidence intentionally does not persist raw visible page text or raw model responses. It keeps safer observation metadata/fingerprints, typed decisions, target resolution, policy outcomes, action events, and terminal status.

This gives enough evidence to audit the run without turning the evidence directory into a store of financial UI data.

---

# Cuts

> **The project prioritizes a complete, defensible vertical slice over feature breadth.**

I deliberately did **not** build:

- native desktop automation,
- VNC/co-browsing operator product UI,
- distributed queues/workers,
- cluster orchestration,
- persistent database-backed capability registry,
- RBAC/SSO,
- external secrets-manager integration,
- full approval workflow,
- cross-tenant override DSL,
- automated multi-run flakiness scoring,
- code-generation stretch goal,
- open-ended LLM repair during replay.

I did implement one optional stretch goal deeply: an **agent-facing capability catalog/invocation API** with typed arguments, exact version lookup, tenant binding, approval gating, deterministic replay, and evidence.

The artifact also includes a real `draft`/approval seam, but I do not claim a complete enterprise approval product.

### What I would build next

1. Unify policy-induced and runtime-induced human escalation behind one persistent same-session intervention service.
2. Add a durable capability/version/approval registry.
3. Implement a second non-DOM `ComputerSurface`.
4. Add vendor/tenant compatibility and drift telemetry.
5. Add a reviewed re-discovery/versioning workflow.
6. Add multi-run reliability/confidence metrics.
7. Build an operator-facing intervention queue/UI.

I would keep deterministic replay as the default production path.

If a capability no longer resolves safely:

```text
stop
  ↓
preserve evidence
  ↓
review / rediscover
  ↓
publish a new capability version
```

rather than silently placing an LLM back into the production execution loop.
