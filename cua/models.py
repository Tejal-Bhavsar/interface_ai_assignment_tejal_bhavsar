from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    EXTRACT = "extract"
    WAIT = "wait"
    ASSERT = "assert"
    COMPLETE = "complete"
    REQUEST_HUMAN = "request_human"


class RiskLevel(str, Enum):
    SAFE = "safe"
    RISKY = "risky"
    IRREVERSIBLE = "irreversible"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_HUMAN = "require_human"
    BLOCK = "block"


class LocatorKind(str, Enum):
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    PLACEHOLDER = "placeholder"
    CSS = "css"
    XPATH = "xpath"
    RELATIVE_TEXT = "relative_text"


class LocatorCandidate(BaseModel):
    kind: LocatorKind

    role: str | None = None
    name: str | None = None
    value: str | None = None

    reference_text: str | None = None
    relation: str | None = None

    exact: bool = True

    frame_hint: str | None = None

    description: str | None = None


class TargetDescriptor(BaseModel):
    description: str

    locators: list[LocatorCandidate] = Field(
        default_factory=list
    )

class ResolvedTargetInfo(BaseModel):
    tag: str | None = None

    role: str | None = None

    text: str | None = None

    name: str | None = None

    aria_label: str | None = None

    placeholder: str | None = None

    href: str | None = None

class PolicyEvaluation(BaseModel):
    decision: PolicyDecision

    risk_level: RiskLevel

    reason: str

    matched_phrase: str | None = None


class ConditionType(str, Enum):
    TEXT_PRESENT = "text_present"
    TEXT_ABSENT = "text_absent"

    ELEMENT_PRESENT = "element_present"
    ELEMENT_ABSENT = "element_absent"

    URL_MATCHES = "url_matches"

    OUTPUT_EXISTS = "output_exists"


class Condition(BaseModel):
    type: ConditionType

    value: str | None = None

    target: TargetDescriptor | None = None

    output_name: str | None = None

    timeout_ms: int = Field(
        default=5000,
        ge=0,
    )


class RetryPolicy(BaseModel):
    max_attempts: int = Field(
        default=1,
        ge=1,
    )

    delay_ms: int = Field(
        default=500,
        ge=0,
    )

    backoff_multiplier: float = Field(
        default=1.0,
        ge=1.0,
    )


class CapabilityStep(BaseModel):
    id: str

    description: str

    action: ActionType

    target: TargetDescriptor | None = None

    value: Any | None = None

    output_name: str | None = None

    preconditions: list[Condition] = Field(
        default_factory=list
    )

    postconditions: list[Condition] = Field(
        default_factory=list
    )

    retry: RetryPolicy = Field(
        default_factory=RetryPolicy
    )

    risk_level: RiskLevel = RiskLevel.SAFE


class ValueType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class TypedField(BaseModel):
    type: ValueType

    description: str

    required: bool = True

    sensitive: bool = False


class OutcomeRule(BaseModel):
    code: str

    description: str

    condition: Condition


class RecoveryStrategy(str, Enum):
    RELOAD = "reload"
    WAIT = "wait"
    DISMISS = "dismiss"
    RETRY_STEP = "retry_step"


class RecoveryRule(BaseModel):
    code: str

    description: str

    condition: Condition

    strategy: RecoveryStrategy

    max_attempts: int = Field(
        default=1,
        ge=1,
    )


class FailureCategory(str, Enum):
    RECOVERABLE = "recoverable"
    HARD_FAILURE = "hard_failure"
    POLICY_BLOCKED = "policy_blocked"


class FailureRule(BaseModel):
    code: str

    description: str

    condition: Condition

    category: FailureCategory = (
        FailureCategory.HARD_FAILURE
    )

    escalate_to_human: bool = False

class ApplicationProfile(BaseModel):
    vendor_family: str

    profile_version: str = "1.0"

    description: str

    business_outcomes: list[OutcomeRule] = Field(
        default_factory=list
    )

    recoveries: list[RecoveryRule] = Field(
        default_factory=list
    )

    failures: list[FailureRule] = Field(
        default_factory=list
    )

class TargetSpec(BaseModel):
    surface_type: str = "web"

    application: str

    vendor_family: str

    entry_point: str


class ApprovalState(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    DISABLED = "disabled"


class CapabilityIdentity(BaseModel):
    id: str

    name: str

    version: str

    description: str

    approval_state: ApprovalState = (
        ApprovalState.DRAFT
    )


class SafetyContract(BaseModel):
    allowed_origins: list[str] = Field(
        default_factory=list
    )

    allowed_routes: list[str] = Field(
        default_factory=list
    )

    allowed_actions: list[ActionType] = Field(
        default_factory=list
    )

    risky_action_mode: Literal[
        "block",
        "require_human",
    ] = "require_human"


class DiscoveryMetadata(BaseModel):
    run_id: str

    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    provider: str

    model: str

    source_tenant: str | None = None

    source_goal_template: str | None = None


class CapabilityArtifact(BaseModel):
    schema_version: str = "1.0"

    identity: CapabilityIdentity

    target: TargetSpec

    inputs: dict[str, TypedField]

    outputs: dict[str, TypedField]

    steps: list[CapabilityStep]

    business_outcomes: list[OutcomeRule] = Field(
        default_factory=list
    )

    recoveries: list[RecoveryRule] = Field(
        default_factory=list
    )

    failures: list[FailureRule] = Field(
        default_factory=list
    )

    checkpoint: Condition

    safety: SafetyContract

    discovery: DiscoveryMetadata

    integrity_sha256: str | None = None


class ObservedControl(BaseModel):
    tag: str

    role: str | None = None

    name: str | None = None

    text: str | None = None

    placeholder: str | None = None

    input_type: str | None = None

    disabled: bool = False


class Observation(BaseModel):
    url: str

    title: str

    visible_text: str

    aria_snapshot: str | None = None

    controls: list[ObservedControl] = Field(
        default_factory=list
    )

    dialog_text: str | None = None


class AgentAction(BaseModel):
    action: ActionType

    target: TargetDescriptor | None = None

    value: Any | None = None

    output_name: str | None = None

    reason: str

    success_condition: Condition | None = None

    risk_hint: RiskLevel = RiskLevel.SAFE


class RunMode(str, Enum):
    DISCOVERY = "discovery"
    REPLAY = "replay"


class RunEvent(BaseModel):
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    run_id: str

    mode: RunMode

    event_type: str

    step_id: str | None = None

    message: str

    data: dict[str, Any] = Field(
        default_factory=dict
    )


class ControlOwner(str, Enum):
    AUTOMATION = "automation"
    HUMAN = "human"
    RESUME_REQUESTED = "resume_requested"


class HumanAction(BaseModel):
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    action_type: str

    target_description: str | None = None

    value: str | None = None


class InterventionRequest(BaseModel):
    id: str

    run_id: str

    capability_id: str | None = None

    goal: str | None = None

    step_id: str | None = None

    reason_code: str

    reason: str

    owner: ControlOwner = ControlOwner.HUMAN

    screenshot_path: str | None = None

    dom_snapshot_path: str | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    human_actions: list[HumanAction] = Field(
        default_factory=list
    )


class SuccessResult(BaseModel):
    status: Literal["success"] = "success"

    run_id: str

    outputs: dict[str, Any] = Field(
        default_factory=dict
    )


class BusinessOutcomeResult(BaseModel):
    status: Literal[
        "business_outcome"
    ] = "business_outcome"

    run_id: str

    code: str

    message: str

    outputs: dict[str, Any] = Field(
        default_factory=dict
    )


class FailureResult(BaseModel):
    status: Literal["failure"] = "failure"

    run_id: str

    category: FailureCategory

    code: str

    message: str

    step_id: str | None = None

    expected: Any | None = None

    observed: Any | None = None

    evidence: dict[str, str] = Field(
        default_factory=dict
    )


class InterventionResult(BaseModel):
    status: Literal[
        "intervention_required"
    ] = "intervention_required"

    run_id: str

    intervention_id: str

    reason_code: str

    message: str


ExecutionResult = (
    SuccessResult
    | BusinessOutcomeResult
    | FailureResult
    | InterventionResult
)



class DiscoveryStatus(
    str,
    Enum,
):
    COMPLETED = "completed"

    INTERVENTION_REQUIRED = (
        "intervention_required"
    )

    POLICY_BLOCKED = (
        "policy_blocked"
    )

    FAILED = "failed"

    MAX_STEPS = "max_steps"


class DiscoveryStepRecord(
    BaseModel
):
    """
    Typed in-memory record of one discovery decision.

    This is NOT the reusable capability artifact.

    Step 10 will compile successful discovery records into a
    separate typed/versioned capability.
    """

    step_index: int = Field(
        ge=1
    )

    url_before: str

    url_after: str | None = None

    action: AgentAction

    policy_evaluation: (
        PolicyEvaluation
        | None
    ) = None

    resolved_target: (
        ResolvedTargetInfo
        | None
    ) = None

    extracted_output_name: (
        str | None
    ) = None

    extracted_output_value: (
        Any | None
    ) = None

    success_condition_passed: (
        bool | None
    ) = None


class DiscoveryRunResult(
    BaseModel
):
    """
    Result of one discovery run.

    Raw values may exist here temporarily in memory.

    Persistent evidence will be redacted later by the
    evidence layer.
    """

    run_id: str

    goal: str

    entry_url: str

    provider: str

    model: str

    status: DiscoveryStatus

    steps: list[
        DiscoveryStepRecord
    ] = Field(
        default_factory=list
    )

    outputs: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )

    message: str