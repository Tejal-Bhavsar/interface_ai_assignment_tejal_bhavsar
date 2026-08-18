Architecture

I built the system around the assignment's central production split: an LLM discovers the task once, a structured artifact captures what was learned, and deterministic replay invokes that capability later without an LLM decision loop. The implementation is a modular monolith because the important problem here is correctness of the control boundaries, not distributed infrastructure.

The end-to-end path is goal + entry URL -> DiscoveryEngine -> live ComputerSurface -> LLM ActionProvider -> CapabilityCompiler -> CapabilityArtifact -> ReplayEngine. ComputerSurface is the UI abstraction; PlaywrightSurface is the concrete browser implementation. Discovery and replay therefore depend on an interaction contract rather than Playwright-specific calls. This gives a credible seam for later desktop/accessibility/image-based surfaces.

DiscoveryEngine owns the genuine observe -> decide -> act loop. Each iteration observes live state, asks the selected LLM provider for one typed AgentAction, resolves the proposed target against the actual live surface, runs deployment policy, executes the action, and observes again. The provider layer supports multiple adapters, but the final required live proof used Gemini 2.5 Flash (disc_22b2281984ae). Discovery evidence records safe observation fingerprints/control summaries, LLM decisions, resolved targets, policy results, action execution, and the final result.

A separate compiler is a deliberate boundary. I did not make the raw discovery transcript the production automation because it contains exploration, concrete runtime values, and model reasoning. The compiler parameterizes invocation data, removes discovery-only control actions, attaches typed inputs/outputs, stable target descriptors, application runtime semantics, checkpoint, safety metadata, provenance, and an integrity SHA. It rejects unsafe compilation instead of trying to repair it silently.

ReplayEngine is the production path and intentionally has no LLM decision dependency. It validates integrity, approval state, typed inputs, artifact safety, runtime policy, target uniqueness, application runtime state, bounded recovery, and final checkpoint. Evidence is passive and cannot choose actions. The complete repository is tested as one integrated vertical slice; the final regression is 120 passing tests.

I also implemented the optional agent-facing capability interface as a small FastAPI catalog/invocation service. It exposes exact capability versions and typed invocation arguments, applies tenant compatibility binding, then executes the deterministic replay path. This is intentionally thin: it demonstrates how an upstream AI agent would invoke a reviewed capability without building unrelated orchestration infrastructure.

Artifact schema

The artifact is a typed, serializable, versioned capability contract, not a macro or transcript. The core CapabilityArtifact contains schema_version; capability identity (id, name, version, description, approval state); target/application metadata; typed inputs; typed outputs; ordered steps; embedded business_outcomes, recoveries, and failures; a checkpoint; safety contract; discovery provenance; and integrity_sha256.

Inputs and outputs include type and sensitivity metadata. During discovery the concrete member ID is known, but the compiler converts that value into the reusable placeholder {{member_id}}. It verifies that every declared input actually affects executable behavior. Concrete sensitive runtime outputs, including the discovered savings balance, are not embedded in the artifact. The example capability therefore says "given a sensitive string member_id, return sensitive string current_savings_balance" rather than containing one member's data.

Each executable step stores a stable ID, description, action, optional target, value/template, output name, conditions, and risk level. TargetDescriptor contains ordered LocatorCandidates. The web implementation supports role/name, label, text, placeholder, relative text, CSS, and XPath, but the compiler/runtime prefer semantic/contextual targeting. For example, the final balance extraction is represented as "Current Balance, same row" rather than the concrete balance text. Resolution must be unique; the engine rejects ambiguous matches rather than calling .first().

Application runtime rules are embedded because they are semantics the deterministic capability must understand: a missing member is a business outcome, session/transient states can be recoverable, permission/application errors are hard failures, and security verification can require a human. In contrast, tenant entry URLs remain outside the artifact. This keeps the artifact immutable and reusable across compatible deployments.

The example capability is version 1.0.0, schema 1.0, approval state draft, with one typed input, one typed output, four executable steps, and an OUTPUT_EXISTS(current_savings_balance) checkpoint. Its final integrity digest is cd2a9e2e522df917c914b5e1d1eb1f312ed171268f95b2dce8f976b82f50a6f5. Draft capabilities are not callable by default; smoke/demo execution must explicitly opt in.

Determinism & error handling

Replay follows only the artifact, typed invocation inputs, deterministic surface operations, runtime rules, and policy. It does not ask a model what to do next. Before execution, replay verifies the artifact SHA, rejects draft capabilities unless explicitly enabled, rejects missing/unknown/wrongly typed inputs, and binds placeholders. Each step is checked against the artifact's own safety contract and the global PolicyEngine.

Target resolution is deterministic and fail-closed. Locator candidates are attempted in declared order, but each candidate must uniquely identify a control. Ambiguity or inability to resolve is an error; replay does not guess. Navigation is also contained: the entry URL is policy-checked before navigation, an explicit action destination can be checked before execution, and the actual browser URL is checked after the action/recovery.

The runtime result taxonomy is first-class. Caller-visible status is completed, business_outcome, failed, or human_required; runtime classification distinguishes normal, business_outcome, recoverable, hard_failure, and human_required. The classifier gives failure/human-required conditions precedence, then recovery, then business outcomes, then normal. A nonexistent member is therefore returned as a legitimate business result rather than a crash. Known session-expired/transient-busy conditions run a bounded deterministic recovery such as reload. Permission denial and application error stop with structured failures. Recovery has max_attempts; no infinite retry loop is possible.

A replay is not considered successful only because its click sequence finished. The declared checkpoint must pass and declared outputs must exist. On failure the evidence recorder writes structured events plus richer masked screenshot and sanitized HTML/structure evidence. I deliberately did not implement LLM self-healing during replay: if the target cannot be resolved safely, the deterministic contract should stop and trigger review/re-discovery rather than silently reintroduce reasoning.

Heterogeneity & multi-tenant

I separated surface, capability, and deployment.

For heterogeneous surfaces, ComputerSurface expresses the actions the rest of the system needs: observe, resolve, navigate/reload, interact, extract, check conditions, and capture evidence. PlaywrightSurface maps those concepts to a browser. A future native/remote desktop surface could map role/name to an accessibility tree, relative text to accessibility/visual relationships, click/fill to OS-level interaction, and structure evidence to accessibility-tree or screenshot-derived state. The artifact remains semantic; only the surface resolver/executor changes. This is more credible than allowing Playwright selectors to leak throughout discovery/compiler/replay.

For multi-tenancy, a reusable capability describes HOW to accomplish a task while a TenantApplicationBinding describes WHERE it may run. Bindings contain tenant/application identity, entry URL, vendor product/compatibility key, enabled state, and allowed capability versions. The same artifact is proven to bind to two compatible tenant instances without mutation; unknown tenants and incompatible application versions fail closed. A future vendor version (legacycore-x:v2) is intentionally incompatible with the current v1 artifact instead of being optimistically executed.

At larger scale I would create a persistent vendor/product/version capability registry and collect compatibility/drift metrics. The default strategy would remain canonical vendor capability plus tenant binding/override only where necessary. I deliberately did not build queues, distributed workers, clusters, or fleet plumbing: the assignment values scalable abstractions, not premature scaling infrastructure.

Escalation & handoff

The implemented handoff is a real control-transfer mechanism, not a TODO. Runtime rules can identify a state that cannot be safely resolved automatically. The demonstrated case is LegacyCore's SECURITY_VERIFICATION modal.

When encountered, replay creates an InterventionRequest containing the intervention ID, capability, step, reason, message, live URL, and resume attempt. Ownership is explicit: AUTOMATION -> WAITING_FOR_HUMAN -> HUMAN -> VALIDATING_RESUME -> AUTOMATION. PlaywrightHumanHandoff keeps the exact existing Page and BrowserContext; the operator acts in the already-open browser rather than recreating the session. Browser instrumentation records sanitized human actions across navigation. The final manual evidence records the human clicking Acknowledge & Continue.

Critically, "human says resume" is only a request. Before returning ownership to automation, the system validates that the browser is still inside the global allowlist, the blocking state is gone, runtime state is acceptable, next-step conditions hold, and the next target resolves uniquely. Resume attempts are bounded; a failed validation leaves ownership with the human rather than blindly continuing. The final evidence bundle contains a real manual same-session run, while --auto exists only for unattended regression.

There is one explicit cut: a policy decision that returns HUMAN_REQUIRED currently stops with a structured replay result before the risky action, while application-runtime HUMAN_REQUIRED is routed through the same-session handoff flow. The next production integration would unify both escalation sources behind one durable intervention/session service so an API invocation can pause and later resume.

Safety

Safety is enforced in layers. The capability's SafetyContract limits the actions/risk envelope it was compiled and reviewed for. Separately, PolicyEngine loads deployment policy from config/policy.json: exact allowed origins, route-prefix allowlists, action allowlist, risky phrases, blocked phrases, and risky-action mode. Replay cannot bypass artifact safety just because deployment policy allows something, and vice versa.

Policy evaluates the actual resolved live target, not only an LLM/artifact description. This matters for risky interfaces: an artifact could describe a button as "Continue" while the live element says "Confirm Open Sub-Account". The real target text/name/href is evaluated. Blocked phrases take precedence over generic risky handling, risky actions can require a human, and IRREVERSIBLE risk is always blocked unattended. URL-prefix matching uses proper path boundaries so /legacy does not accidentally allow lookalike paths such as /legacy-evil. Destination URLs and post-action URLs are checked as defense in depth.

Data handling is equally conservative. Typed fields can be marked sensitive; the compiler prevents concrete sensitive discovery inputs/outputs from being embedded in the reusable artifact. Replay evidence redacts sensitive inputs/outputs, known runtime values, member IDs in URLs, and sensitive query parameters. Failure screenshots mask [data-sensitive=true]; structural HTML is sanitized. Discovery evidence intentionally avoids raw visible page text and raw model responses, persisting only safer observation metadata/fingerprints, typed decisions, target resolution, policy results, and action events. This gives auditable proof without making logs a repository of financial UI data.

Cuts

The project intentionally focuses on a complete, defensible vertical slice. I did not build a native desktop backend, VNC/co-browsing operator product, persistent database-backed capability registry, distributed job queues/workers, RBAC/SSO, external secrets manager, full approval workflow, cross-tenant override DSL, automated multi-run flakiness scoring, or code-generation stretch goal. I also did not implement open-ended LLM repair during replay.

I did implement one stretch goal deeply: an agent-facing capability catalog/invocation API with typed arguments, exact version lookup, tenant binding, approval gating, deterministic replay, and evidence. The artifact also has a real draft/approval seam, but I do not claim a complete confidence/approval product.

With more time, my first change would be to unify policy-induced and runtime-induced human escalation behind one persistent same-session intervention service. Next I would add a durable capability/version/approval registry and vendor/tenant drift telemetry, then implement a second non-DOM ComputerSurface to validate the abstraction against desktop/remote software. I would add multi-run reliability metrics before considering any assisted fallback. If a deterministic capability no longer resolves safely, my default remains: stop, preserve evidence, review/re-discover, and publish a new capability version rather than silently placing an LLM back into production execution.