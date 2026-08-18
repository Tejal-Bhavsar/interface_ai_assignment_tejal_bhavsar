from __future__ import annotations

import time
import uuid

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from cua.compiler import verify_artifact_integrity
from cua.evidence import EvidenceRecorder
from cua.handoff import (
    HandoffStatus,
    HumanActionRecord,
    HumanHandoffHandler,
    InterventionRequest,
    ResumeValidationResult,
)
from cua.models import (
    ActionType,
    CapabilityArtifact,
    CapabilityStep,
    Condition,
    FailureRule,
    OutcomeRule,
    PolicyDecision,
    RecoveryRule,
    ValueType,
)
from cua.policy import (
    PolicyEngine,
    PolicyEvaluation,
)
from cua.surface import (
    ComputerSurface,
    ResolvedTarget,
)


# ============================================================
# Errors
# ============================================================


class ReplayError(RuntimeError):
    """Base error for deterministic capability replay."""

    pass


class ReplayIntegrityError(ReplayError):
    pass


class ReplayApprovalError(ReplayError):
    pass


class ReplayInputError(ReplayError):
    pass


class ReplayStepError(ReplayError):
    pass


class ReplayCheckpointError(ReplayError):
    pass


class ReplaySafetyError(ReplayError):
    pass


# ============================================================
# Replay result taxonomy
# ============================================================


class ReplayStatus(str, Enum):
    """Final caller-visible replay status."""

    COMPLETED = "completed"
    BUSINESS_OUTCOME = "business_outcome"
    FAILED = "failed"
    HUMAN_REQUIRED = "human_required"


class RuntimeStateKind(str, Enum):
    """Classification of the current application runtime state."""

    NORMAL = "normal"
    BUSINESS_OUTCOME = "business_outcome"
    RECOVERABLE = "recoverable"
    HARD_FAILURE = "hard_failure"
    HUMAN_REQUIRED = "human_required"


class RuntimeStateMatch(BaseModel):
    """
    Structured semantic runtime-state match.

    Raw HTML and sensitive customer data are intentionally not
    stored here.
    """

    kind: RuntimeStateKind
    code: str
    message: str
    matched_text: str | None = None

    recovery_action: str | None = None
    recovery_attempt: int = 0
    recovery_max_attempts: int | None = None


class ReplayStepRecord(BaseModel):
    step_id: str
    action: ActionType
    status: str

    url: str | None = None
    output_name: str | None = None
    message: str | None = None


class ReplayResult(BaseModel):
    """
    Structured caller-facing result of deterministic replay.

    A caller can distinguish:
      - completed
      - business_outcome
      - failed
      - human_required
    """

    capability_id: str
    capability_version: str
    status: ReplayStatus

    outputs: dict[str, Any] = Field(
        default_factory=dict
    )

    steps: list[ReplayStepRecord] = Field(
        default_factory=list
    )

    checkpoint_passed: bool = False

    runtime_state: RuntimeStateMatch | None = None

    recovery_count: int = 0

    human_intervention_count: int = 0

    human_resume_attempt_count: int = 0

    human_actions: list[
        HumanActionRecord
    ] = Field(
        default_factory=list
    )

    failed_step_id: str | None = None

    message: str


# ============================================================
# Type validation
# ============================================================


def _matches_value_type(
    value: Any,
    value_type: ValueType,
) -> bool:
    if value is None:
        return False

    if value_type == ValueType.STRING:
        return isinstance(
            value,
            str,
        )

    if value_type == ValueType.NUMBER:
        return (
            isinstance(
                value,
                (int, float),
            )
            and not isinstance(
                value,
                bool,
            )
        )

    if value_type == ValueType.BOOLEAN:
        return isinstance(
            value,
            bool,
        )

    if value_type == ValueType.OBJECT:
        return isinstance(
            value,
            Mapping,
        )

    if value_type == ValueType.ARRAY:
        return (
            isinstance(
                value,
                Sequence,
            )
            and not isinstance(
                value,
                (
                    str,
                    bytes,
                    bytearray,
                ),
            )
        )

    return False


# ============================================================
# Placeholder binding
# ============================================================


def _placeholder(
    name: str,
) -> str:
    return (
        "{{"
        + name
        + "}}"
    )


def _bind_value(
    value: Any,
    inputs: dict[str, Any],
) -> Any:
    """
    Deterministically replace capability placeholders.

    Exact placeholder:
        "{{member_id}}"

    returns the original typed runtime value.

    Embedded placeholder:
        "/member/{{member_id}}"

    becomes:
        "/member/1002"
    """

    if isinstance(
        value,
        str,
    ):
        # Exact placeholder preserves the typed runtime value.
        for (
            name,
            runtime_value,
        ) in inputs.items():
            token = _placeholder(
                name
            )

            if value == token:
                return runtime_value

        # Embedded placeholders become string replacements.
        result = value

        for (
            name,
            runtime_value,
        ) in inputs.items():
            result = result.replace(
                _placeholder(
                    name
                ),
                str(
                    runtime_value
                ),
            )

        return result

    if isinstance(
        value,
        Mapping,
    ):
        return {
            key: _bind_value(
                item,
                inputs,
            )
            for (
                key,
                item,
            ) in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            _bind_value(
                item,
                inputs,
            )
            for item in value
        ]

    if isinstance(
        value,
        tuple,
    ):
        return tuple(
            _bind_value(
                item,
                inputs,
            )
            for item in value
        )

    return value


def _bind_step(
    step: CapabilityStep,
    inputs: dict[str, Any],
) -> CapabilityStep:
    data = step.model_dump(
        mode="json"
    )

    bound = _bind_value(
        data,
        inputs,
    )

    return CapabilityStep.model_validate(
        bound
    )


def _bind_condition(
    condition: Condition,
    inputs: dict[str, Any],
) -> Condition:
    data = condition.model_dump(
        mode="json"
    )

    bound = _bind_value(
        data,
        inputs,
    )

    return Condition.model_validate(
        bound
    )


# ============================================================
# Runtime application-state classifier
# ============================================================


class RuntimeClassifier:
    """
    Deterministically classify the current application state
    using rules embedded in the saved capability artifact.

    No LLM is involved.

    Conservative precedence:
        1. failure / human-required
        2. recoverable
        3. business outcome
        4. normal
    """

    def __init__(
        self,
        *,
        surface: ComputerSurface,
    ):
        self.surface = surface

    async def _matches(
        self,
        condition: Condition,
        outputs: dict[str, Any],
    ) -> bool:
        """
        Classification asks what is visible RIGHT NOW.

        Runtime profile conditions may normally have a timeout,
        but waiting for every non-matching rule after every step
        would make deterministic replay unnecessarily slow.
        """

        immediate_condition = (
            condition.model_copy(
                update={
                    "timeout_ms": 0
                }
            )
        )

        return (
            await self
            .surface
            .check_condition(
                immediate_condition,
                outputs,
            )
        )

    async def _match_failure(
        self,
        rules: list[FailureRule],
        outputs: dict[str, Any],
    ) -> RuntimeStateMatch | None:
        for rule in rules:
            if not await self._matches(
                rule.condition,
                outputs,
            ):
                continue

            if rule.escalate_to_human:
                return RuntimeStateMatch(
                    kind=(
                        RuntimeStateKind
                        .HUMAN_REQUIRED
                    ),
                    code=rule.code,
                    message=rule.description,
                    matched_text=(
                        rule.condition.value
                    ),
                )

            return RuntimeStateMatch(
                kind=(
                    RuntimeStateKind
                    .HARD_FAILURE
                ),
                code=rule.code,
                message=rule.description,
                matched_text=(
                    rule.condition.value
                ),
            )

        return None

    async def _match_recovery(
        self,
        rules: list[RecoveryRule],
        outputs: dict[str, Any],
    ) -> RuntimeStateMatch | None:
        for rule in rules:
            if not await self._matches(
                rule.condition,
                outputs,
            ):
                continue

            return RuntimeStateMatch(
                kind=(
                    RuntimeStateKind
                    .RECOVERABLE
                ),
                code=rule.code,
                message=rule.description,
                matched_text=(
                    rule.condition.value
                ),
                recovery_action=(
                    rule.strategy.value
                ),
                recovery_max_attempts=(
                    rule.max_attempts
                ),
            )

        return None

    async def _match_business_outcome(
        self,
        rules: list[OutcomeRule],
        outputs: dict[str, Any],
    ) -> RuntimeStateMatch | None:
        for rule in rules:
            if not await self._matches(
                rule.condition,
                outputs,
            ):
                continue

            return RuntimeStateMatch(
                kind=(
                    RuntimeStateKind
                    .BUSINESS_OUTCOME
                ),
                code=rule.code,
                message=rule.description,
                matched_text=(
                    rule.condition.value
                ),
            )

        return None

    async def classify(
        self,
        *,
        artifact: CapabilityArtifact,
        outputs: dict[str, Any],
    ) -> RuntimeStateMatch:
        # Fail closed: failures have highest precedence.
        failure = (
            await self
            ._match_failure(
                artifact.failures,
                outputs,
            )
        )

        if failure is not None:
            return failure

        recovery = (
            await self
            ._match_recovery(
                artifact.recoveries,
                outputs,
            )
        )

        if recovery is not None:
            return recovery

        business_outcome = (
            await self
            ._match_business_outcome(
                artifact.business_outcomes,
                outputs,
            )
        )

        if business_outcome is not None:
            return business_outcome

        return RuntimeStateMatch(
            kind=RuntimeStateKind.NORMAL,
            code="NORMAL",
            message=(
                "No exceptional runtime "
                "state detected."
            ),
        )


# ============================================================
# Replay engine
# ============================================================


class ReplayEngine:
    """
    Execute a compiled capability deterministically.

    IMPORTANT:
    This module intentionally contains no LLM dependency.

    Replay follows only:
      - the saved artifact
      - supplied typed inputs
      - deterministic surface operations
      - embedded runtime rules
      - recorded conditions/checkpoints
    """

    def __init__(
        self,
        *,
        surface: ComputerSurface,
        entry_url: str,
        allow_draft: bool = False,
        evidence: EvidenceRecorder | None = None,
        handoff: HumanHandoffHandler | None = None,
        policy: PolicyEngine | None = None,
        max_handoff_resume_attempts: int = 3,
    ):
        """
        entry_url is runtime/deployment configuration.

        It is not learned or selected by an LLM, allowing the
        same reusable capability to target different deployments
        of the same application.

        evidence is optional observability only. It never makes
        replay decisions.
        """

        if not entry_url.strip():
            raise ReplayError(
                "Replay entry_url cannot be empty."
            )

        self.surface = surface

        self.runtime_classifier = (
            RuntimeClassifier(
                surface=surface
            )
        )

        self.entry_url = entry_url
        self.allow_draft = allow_draft
        self.evidence = evidence
        self.handoff = handoff
        self.policy = policy

        if max_handoff_resume_attempts < 1:
            raise ReplayError(
                (
                    "max_handoff_resume_attempts "
                    "must be at least 1."
                )
            )

        self.max_handoff_resume_attempts = (
            max_handoff_resume_attempts
        )

    # --------------------------------------------------------
    # Artifact validation
    # --------------------------------------------------------

    def _validate_artifact(
        self,
        artifact: CapabilityArtifact,
    ) -> None:
        if not verify_artifact_integrity(
            artifact
        ):
            raise ReplayIntegrityError(
                (
                    "Capability artifact "
                    "integrity verification "
                    "failed."
                )
            )

        approval_state = (
            artifact
            .identity
            .approval_state
            .value
        )

        if (
            approval_state == "draft"
            and not self.allow_draft
        ):
            raise ReplayApprovalError(
                (
                    "Draft capabilities "
                    "cannot be replayed by "
                    "default."
                )
            )

    # --------------------------------------------------------
    # Input validation
    # --------------------------------------------------------

    @staticmethod
    def _validate_inputs(
        artifact: CapabilityArtifact,
        inputs: dict[str, Any],
    ) -> None:
        expected = set(
            artifact.inputs
        )

        supplied = set(
            inputs
        )

        missing = (
            expected
            - supplied
        )

        unknown = (
            supplied
            - expected
        )

        if missing:
            raise ReplayInputError(
                (
                    "Missing capability "
                    "inputs: "
                    f"{sorted(missing)}"
                )
            )

        if unknown:
            raise ReplayInputError(
                (
                    "Unknown capability "
                    "inputs: "
                    f"{sorted(unknown)}"
                )
            )

        for (
            name,
            field,
        ) in artifact.inputs.items():
            value = inputs[
                name
            ]

            if not _matches_value_type(
                value,
                field.type,
            ):
                raise ReplayInputError(
                    (
                        f"Input '{name}' "
                        "does not match "
                        f"declared type "
                        f"'{field.type.value}'."
                    )
                )

    # --------------------------------------------------------
    # Artifact-level safety
    # --------------------------------------------------------

    def _validate_step_safety(
        self,
        artifact: CapabilityArtifact,
        step: CapabilityStep,
    ) -> None:
        """
        Fail closed for actions outside the capability's own
        safety contract.

        Global PolicyEngine enforcement is a separate boundary.
        """

        allowed_actions = getattr(
            artifact.safety,
            "allowed_actions",
            None,
        )

        if (
            allowed_actions is not None
            and step.action
            not in allowed_actions
        ):
            raise ReplaySafetyError(
                (
                    f"Action '{step.action.value}' "
                    "is not allowed by the "
                    "capability safety contract."
                )
            )

        risk_value = (
            step.risk_level.value
            if step.risk_level
            is not None
            else "safe"
        )

        # If no global runtime policy was supplied, retain the
        # conservative historical behavior and fail closed.
        #
        # When a PolicyEngine is present, it becomes the runtime
        # authority for risky/irreversible treatment while the
        # artifact-level allowed_actions contract above remains
        # independently enforced.
        if (
            self.policy is None
            and risk_value in {
                "risky",
                "irreversible",
            }
        ):
            raise ReplaySafetyError(
                (
                    f"Step '{step.id}' "
                    f"has risk level "
                    f"'{risk_value}' and "
                    "cannot run without a "
                    "global policy decision."
                )
            )

    # --------------------------------------------------------
    # Global runtime policy
    # --------------------------------------------------------

    @staticmethod
    def _policy_runtime_state(
        evaluation: PolicyEvaluation,
    ) -> RuntimeStateMatch:
        if (
            evaluation.decision
            == PolicyDecision
            .REQUIRE_HUMAN
        ):
            kind = (
                RuntimeStateKind
                .HUMAN_REQUIRED
            )
        else:
            kind = (
                RuntimeStateKind
                .HARD_FAILURE
            )

        return RuntimeStateMatch(
            kind=kind,
            code=evaluation.code,
            message=evaluation.reason,
            matched_text=(
                evaluation
                .matched_phrase
            ),
        )

    def _record_policy_evaluation(
        self,
        *,
        evaluation: PolicyEvaluation,
        step_id: str | None,
        action: ActionType | None,
    ) -> None:
        if self.evidence is None:
            return

        self.evidence.record_event(
            event_type=(
                "policy_evaluated"
            ),
            step_id=step_id,
            action=(
                action.value
                if action is not None
                else None
            ),
            status=(
                evaluation
                .decision
                .value
            ),
            url=(
                self.surface
                .current_url
            ),
            runtime_state_code=(
                evaluation.code
            ),
            message=(
                evaluation.reason
            ),
            data={
                "decision":
                    (
                        evaluation
                        .decision
                        .value
                    ),
                "risk_level":
                    (
                        evaluation
                        .risk_level
                        .value
                    ),
                "matched_phrase":
                    (
                        evaluation
                        .matched_phrase
                    ),
                "current_url_allowed":
                    (
                        evaluation
                        .current_url_allowed
                    ),
                "destination_url_allowed":
                    (
                        evaluation
                        .destination_url_allowed
                    ),
                "evaluated_live_target":
                    (
                        evaluation
                        .evaluated_live_target
                    ),
            },
        )

    async def _evaluate_policy_for_step(
        self,
        step: CapabilityStep,
    ) -> tuple[
        PolicyEvaluation | None,
        ResolvedTarget | None,
    ]:
        """
        Evaluate global runtime policy before the recorded action
        executes.

        Target-bearing actions are resolved first so policy sees
        the actual live element semantics instead of trusting only
        the artifact's target description.
        """

        if self.policy is None:
            return (
                None,
                None,
            )

        action = step.action

        if action == ActionType.NAVIGATE:
            if not isinstance(
                step.value,
                str,
            ):
                raise ReplayStepError(
                    (
                        "NAVIGATE step "
                        "requires a URL value."
                    )
                )

            return (
                self.policy
                .evaluate_navigation(
                    step.value
                ),
                None,
            )

        # WAIT has no target, but is still checked against the
        # allowed action set and current URL.
        if action == ActionType.WAIT:
            return (
                self.policy
                .evaluate_action(
                    action=action,
                    current_url=(
                        self.surface
                        .current_url
                    ),
                    risk_level=(
                        step.risk_level
                    ),
                ),
                None,
            )

        if step.target is None:
            # Keep the replay step error semantics for malformed
            # artifacts rather than fabricating target metadata.
            return (
                self.policy
                .evaluate_action(
                    action=action,
                    current_url=(
                        self.surface
                        .current_url
                    ),
                    risk_level=(
                        step.risk_level
                    ),
                ),
                None,
            )

        resolved = (
            await self
            .surface
            .resolve_target(
                step.target
            )
        )

        destination_url = None

        if (
            action
            == ActionType.CLICK
        ):
            destination_url = (
                resolved.info.href
            )

        evaluation = (
            self.policy
            .evaluate_action(
                action=action,
                current_url=(
                    self.surface
                    .current_url
                ),
                risk_level=(
                    step.risk_level
                ),
                target_description=(
                    step
                    .target
                    .description
                ),
                resolved_info=(
                    resolved.info
                ),
                destination_url=(
                    destination_url
                ),
            )
        )

        return (
            evaluation,
            resolved,
        )

    # --------------------------------------------------------
    # Conditions
    # --------------------------------------------------------

    async def _check_conditions(
        self,
        conditions: list[Condition],
        outputs: dict[str, Any],
        *,
        label: str,
        step_id: str,
    ) -> None:
        for condition in conditions:
            passed = (
                await self
                .surface
                .check_condition(
                    condition,
                    outputs,
                )
            )

            if not passed:
                raise ReplayStepError(
                    (
                        f"{label} failed "
                        f"for step "
                        f"'{step_id}': "
                        f"{condition.type.value}"
                    )
                )

    # --------------------------------------------------------
    # Execute one deterministic step
    # --------------------------------------------------------

    async def _execute_step(
        self,
        step: CapabilityStep,
        outputs: dict[str, Any],
        *,
        resolved_target: (
            ResolvedTarget
            | None
        ) = None,
    ) -> None:
        action = step.action

        # NAVIGATE
        if action == ActionType.NAVIGATE:
            if not isinstance(
                step.value,
                str,
            ):
                raise ReplayStepError(
                    (
                        "NAVIGATE step "
                        "requires a URL value."
                    )
                )

            await self.surface.navigate(
                step.value
            )
            return

        # WAIT is the only non-navigation action below that
        # does not require a target.
        if action == ActionType.WAIT:
            try:
                milliseconds = int(
                    step.value
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ReplayStepError(
                    (
                        "WAIT step requires "
                        "milliseconds."
                    )
                ) from exc

            await self.surface.wait(
                milliseconds
            )
            return

        if step.target is None:
            raise ReplayStepError(
                (
                    f"Step '{step.id}' "
                    "requires a target."
                )
            )

        resolved = (
            resolved_target
            if (
                resolved_target
                is not None
            )
            else (
                await self
                .surface
                .resolve_target(
                    step.target
                )
            )
        )

        # CLICK
        if action == ActionType.CLICK:
            await self.surface.click(
                resolved
            )
            return

        # FILL
        if action == ActionType.FILL:
            if step.value is None:
                raise ReplayStepError(
                    (
                        "FILL step requires "
                        "a value."
                    )
                )

            await self.surface.fill(
                resolved,
                str(
                    step.value
                ),
            )
            return

        # SELECT
        if action == ActionType.SELECT:
            if step.value is None:
                raise ReplayStepError(
                    (
                        "SELECT step requires "
                        "a value."
                    )
                )

            await self.surface.select(
                resolved,
                str(
                    step.value
                ),
            )
            return

        # EXTRACT
        if action == ActionType.EXTRACT:
            if not step.output_name:
                raise ReplayStepError(
                    (
                        "EXTRACT step requires "
                        "output_name."
                    )
                )

            extracted = (
                await self
                .surface
                .extract_text(
                    resolved
                )
            )

            outputs[
                step.output_name
            ] = extracted
            return

        # ASSERT semantics live in deterministic recorded
        # preconditions/postconditions.
        if action == ActionType.ASSERT:
            return

        # Discovery-only and human-owned actions are never
        # silently executed during replay.
        raise ReplayStepError(
            (
                "Unsupported deterministic "
                f"replay action: "
                f"{action.value}"
            )
        )

    # --------------------------------------------------------
    # Runtime recovery
    # --------------------------------------------------------

    @staticmethod
    def _find_recovery_rule(
        artifact: CapabilityArtifact,
        code: str,
    ) -> RecoveryRule | None:
        for rule in artifact.recoveries:
            if rule.code == code:
                return rule

        return None

    async def _classify_with_recovery(
        self,
        *,
        artifact: CapabilityArtifact,
        outputs: dict[str, Any],
        recovery_attempts: dict[str, int],
        step_id: str,
    ) -> tuple[
        RuntimeStateMatch,
        int,
    ]:
        """
        Classify the current UI and automatically perform a
        bounded deterministic recovery when the artifact permits
        it.

        Returns:
            (final runtime state, recoveries performed)
        """

        recoveries_performed = 0

        state = (
            await self
            .runtime_classifier
            .classify(
                artifact=artifact,
                outputs=outputs,
            )
        )

        while (
            state.kind
            == RuntimeStateKind.RECOVERABLE
        ):
            rule = self._find_recovery_rule(
                artifact,
                state.code,
            )

            if rule is None:
                return (
                    RuntimeStateMatch(
                        kind=(
                            RuntimeStateKind
                            .HARD_FAILURE
                        ),
                        code=(
                            "RECOVERY_RULE_MISSING"
                        ),
                        message=(
                            "A recoverable runtime "
                            "state was detected but "
                            "its recovery rule could "
                            "not be found."
                        ),
                        matched_text=(
                            state.matched_text
                        ),
                    ),
                    recoveries_performed,
                )

            attempts_used = (
                recovery_attempts.get(
                    rule.code,
                    0,
                )
            )

            if (
                attempts_used
                >= rule.max_attempts
            ):
                return (
                    state.model_copy(
                        update={
                            "recovery_attempt":
                                attempts_used,
                            "recovery_max_attempts":
                                rule.max_attempts,
                        }
                    ),
                    recoveries_performed,
                )

            attempt_number = (
                attempts_used
                + 1
            )

            recovery_attempts[
                rule.code
            ] = attempt_number

            strategy = (
                rule.strategy.value
            )

            if self.evidence is not None:
                self.evidence.record_event(
                    event_type="recovery_started",
                    step_id=step_id,
                    status="started",
                    url=(
                        self.surface
                        .current_url
                    ),
                    runtime_state_code=(
                        state.code
                    ),
                    recovery_action=(
                        strategy
                    ),
                    recovery_attempt=(
                        attempt_number
                    ),
                    message=(
                        state.message
                    ),
                    data={
                        "max_attempts":
                            rule.max_attempts,
                    },
                )

            if strategy == "reload":
                if self.policy is not None:
                    before_reload_policy = (
                        self.policy
                        .evaluate_current_url(
                            self.surface
                            .current_url
                        )
                    )

                    self._record_policy_evaluation(
                        evaluation=(
                            before_reload_policy
                        ),
                        step_id=step_id,
                        action=None,
                    )

                    if (
                        before_reload_policy
                        .decision
                        != PolicyDecision.ALLOW
                    ):
                        return (
                            self
                            ._policy_runtime_state(
                                before_reload_policy
                            ),
                            recoveries_performed,
                        )

                await self.surface.reload()

                if self.policy is not None:
                    after_reload_policy = (
                        self.policy
                        .evaluate_current_url(
                            self.surface
                            .current_url
                        )
                    )

                    self._record_policy_evaluation(
                        evaluation=(
                            after_reload_policy
                        ),
                        step_id=step_id,
                        action=None,
                    )

                    if (
                        after_reload_policy
                        .decision
                        != PolicyDecision.ALLOW
                    ):
                        return (
                            self
                            ._policy_runtime_state(
                                after_reload_policy
                            ),
                            recoveries_performed,
                        )

            else:
                return (
                    RuntimeStateMatch(
                        kind=(
                            RuntimeStateKind
                            .HARD_FAILURE
                        ),
                        code=(
                            "UNSUPPORTED_RECOVERY_STRATEGY"
                        ),
                        message=(
                            "Replay does not support "
                            f"recovery strategy "
                            f"'{strategy}'."
                        ),
                        matched_text=(
                            state.matched_text
                        ),
                        recovery_action=(
                            strategy
                        ),
                        recovery_attempt=(
                            attempt_number
                        ),
                        recovery_max_attempts=(
                            rule.max_attempts
                        ),
                    ),
                    recoveries_performed,
                )

            recoveries_performed += 1

            if self.evidence is not None:
                self.evidence.record_event(
                    event_type="recovery_completed",
                    step_id=step_id,
                    status="completed",
                    url=(
                        self.surface
                        .current_url
                    ),
                    runtime_state_code=(
                        state.code
                    ),
                    recovery_action=(
                        strategy
                    ),
                    recovery_attempt=(
                        attempt_number
                    ),
                )

            state = (
                await self
                .runtime_classifier
                .classify(
                    artifact=artifact,
                    outputs=outputs,
                )
            )

        return (
            state,
            recoveries_performed,
        )

    # --------------------------------------------------------
    # Human resume validation
    # --------------------------------------------------------

    async def _validate_resume_state(
        self,
        *,
        artifact: CapabilityArtifact,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        recovery_attempts: dict[str, int],
        current_step_index: int,
        current_step_id: str,
        attempt: int,
    ) -> tuple[
        ResumeValidationResult,
        RuntimeStateMatch,
        int,
    ]:
        """
        Validate the live session after a human requests resume.

        Pressing Enter / releasing human control is only a
        request. Automation resumes only when:

          1. no exceptional runtime state remains,
          2. the next recorded step's preconditions hold, and
          3. the next recorded target can still be resolved
             uniquely when that step has a target.

        This is artifact-driven and contains no tenant/member-
        specific URL or value hardcoding.
        """

        if self.policy is not None:
            resume_url_policy = (
                self.policy
                .evaluate_current_url(
                    self.surface
                    .current_url
                )
            )

            self._record_policy_evaluation(
                evaluation=(
                    resume_url_policy
                ),
                step_id=(
                    current_step_id
                ),
                action=None,
            )

            if (
                resume_url_policy
                .decision
                != PolicyDecision.ALLOW
            ):
                policy_state = (
                    self
                    ._policy_runtime_state(
                        resume_url_policy
                    )
                )

                return (
                    ResumeValidationResult(
                        passed=False,
                        attempt=attempt,
                        message=(
                            "Resume rejected because "
                            "the human-controlled "
                            "session is outside the "
                            "configured runtime "
                            "allowlist."
                        ),
                        current_url=(
                            self.surface
                            .current_url
                        ),
                        runtime_state_code=(
                            policy_state.code
                        ),
                    ),
                    policy_state,
                    0,
                )

        (
            runtime_state,
            recoveries_performed,
        ) = (
            await self
            ._classify_with_recovery(
                artifact=artifact,
                outputs=outputs,
                recovery_attempts=(
                    recovery_attempts
                ),
                step_id=(
                    current_step_id
                ),
            )
        )

        if (
            runtime_state.kind
            != RuntimeStateKind.NORMAL
        ):
            return (
                ResumeValidationResult(
                    passed=False,
                    attempt=attempt,
                    message=(
                        "Resume rejected because "
                        "the live application is "
                        "still in runtime state "
                        f"'{runtime_state.code}'."
                    ),
                    current_url=(
                        self.surface
                        .current_url
                    ),
                    runtime_state_code=(
                        runtime_state.code
                    ),
                ),
                runtime_state,
                recoveries_performed,
            )

        next_index = (
            current_step_index + 1
        )

        if (
            next_index
            >= len(
                artifact.steps
            )
        ):
            return (
                ResumeValidationResult(
                    passed=True,
                    attempt=attempt,
                    message=(
                        "Resume state is valid; "
                        "no remaining step target "
                        "must be resolved before "
                        "checkpoint validation."
                    ),
                    current_url=(
                        self.surface
                        .current_url
                    ),
                    runtime_state_code=(
                        runtime_state.code
                    ),
                ),
                runtime_state,
                recoveries_performed,
            )

        next_step = _bind_step(
            artifact.steps[
                next_index
            ],
            inputs,
        )

        for condition in (
            next_step.preconditions
        ):
            passed = (
                await self
                .surface
                .check_condition(
                    condition,
                    outputs,
                )
            )

            if not passed:
                return (
                    ResumeValidationResult(
                        passed=False,
                        attempt=attempt,
                        message=(
                            "Resume rejected because "
                            "a precondition for the "
                            "next deterministic step "
                            "is not satisfied."
                        ),
                        current_url=(
                            self.surface
                            .current_url
                        ),
                        next_step_id=(
                            next_step.id
                        ),
                        next_target_description=(
                            (
                                next_step
                                .target
                                .description
                            )
                            if (
                                next_step.target
                                is not None
                            )
                            else None
                        ),
                        runtime_state_code=(
                            runtime_state.code
                        ),
                    ),
                    runtime_state,
                    recoveries_performed,
                )

        if next_step.target is not None:
            try:
                await (
                    self.surface
                    .resolve_target(
                        next_step.target
                    )
                )

            except Exception:
                return (
                    ResumeValidationResult(
                        passed=False,
                        attempt=attempt,
                        message=(
                            "Resume rejected because "
                            "the expected continuation "
                            "target is not available "
                            "on the current live page. "
                            "Return the browser to the "
                            "expected capability state "
                            "and request resume again."
                        ),
                        current_url=(
                            self.surface
                            .current_url
                        ),
                        next_step_id=(
                            next_step.id
                        ),
                        next_target_description=(
                            next_step
                            .target
                            .description
                        ),
                        runtime_state_code=(
                            runtime_state.code
                        ),
                    ),
                    runtime_state,
                    recoveries_performed,
                )

        return (
            ResumeValidationResult(
                passed=True,
                attempt=attempt,
                message=(
                    "Resume validation passed. "
                    "The next deterministic "
                    "continuation is available."
                ),
                current_url=(
                    self.surface
                    .current_url
                ),
                next_step_id=(
                    next_step.id
                ),
                next_target_description=(
                    (
                        next_step
                        .target
                        .description
                    )
                    if (
                        next_step.target
                        is not None
                    )
                    else None
                ),
                runtime_state_code=(
                    runtime_state.code
                ),
            ),
            runtime_state,
            recoveries_performed,
        )

    # --------------------------------------------------------
    # Runtime terminal-result conversion
    # --------------------------------------------------------

    @staticmethod
    def _runtime_terminal_result(
        *,
        artifact: CapabilityArtifact,
        state: RuntimeStateMatch,
        outputs: dict[str, Any],
        records: list[ReplayStepRecord],
        recovery_count: int,
        step_id: str,
    ) -> ReplayResult:
        if (
            state.kind
            == RuntimeStateKind
            .BUSINESS_OUTCOME
        ):
            return ReplayResult(
                capability_id=(
                    artifact.identity.id
                ),
                capability_version=(
                    artifact.identity.version
                ),
                status=(
                    ReplayStatus
                    .BUSINESS_OUTCOME
                ),
                outputs=outputs,
                steps=records,
                checkpoint_passed=False,
                runtime_state=state,
                recovery_count=(
                    recovery_count
                ),
                failed_step_id=None,
                message=(
                    "Replay ended with a "
                    "known business outcome."
                ),
            )

        if (
            state.kind
            == RuntimeStateKind
            .HUMAN_REQUIRED
        ):
            return ReplayResult(
                capability_id=(
                    artifact.identity.id
                ),
                capability_version=(
                    artifact.identity.version
                ),
                status=(
                    ReplayStatus
                    .HUMAN_REQUIRED
                ),
                outputs=outputs,
                steps=records,
                checkpoint_passed=False,
                runtime_state=state,
                recovery_count=(
                    recovery_count
                ),
                failed_step_id=step_id,
                message=(
                    "Replay requires human "
                    "intervention."
                ),
            )

        # HARD_FAILURE, including an exhausted recoverable
        # condition, is caller-visible failure.
        return ReplayResult(
            capability_id=(
                artifact.identity.id
            ),
            capability_version=(
                artifact.identity.version
            ),
            status=ReplayStatus.FAILED,
            outputs=outputs,
            steps=records,
            checkpoint_passed=False,
            runtime_state=state,
            recovery_count=(
                recovery_count
            ),
            failed_step_id=step_id,
            message=(
                "Replay stopped because "
                "of a runtime failure."
            ),
        )

    # --------------------------------------------------------
    # Replay
    # --------------------------------------------------------

    async def run(
        self,
        *,
        artifact: CapabilityArtifact,
        inputs: dict[str, Any],
    ) -> ReplayResult:
        self._validate_artifact(
            artifact
        )

        self._validate_inputs(
            artifact,
            inputs,
        )

        outputs: dict[
            str,
            Any,
        ] = {}

        records: list[
            ReplayStepRecord
        ] = []

        recovery_attempts: dict[
            str,
            int,
        ] = {}

        total_recovery_count = 0

        human_intervention_count = 0

        human_resume_attempt_count = 0

        human_action_records: list[
            HumanActionRecord
        ] = []

        if self.evidence is not None:
            self.evidence.start_run(
                artifact=artifact,
                inputs=inputs,
                entry_url=self.entry_url,
            )

        try:
            # Runtime/deployment binding. No LLM decides this URL.
            #
            # Global policy checks the deployment URL BEFORE the
            # browser is allowed to navigate.
            if self.policy is not None:
                entry_policy = (
                    self.policy
                    .evaluate_navigation(
                        self.entry_url
                    )
                )

                self._record_policy_evaluation(
                    evaluation=(
                        entry_policy
                    ),
                    step_id=None,
                    action=(
                        ActionType.NAVIGATE
                    ),
                )

                if (
                    entry_policy.decision
                    != PolicyDecision.ALLOW
                ):
                    state = (
                        self
                        ._policy_runtime_state(
                            entry_policy
                        )
                    )

                    result = (
                        self
                        ._runtime_terminal_result(
                            artifact=artifact,
                            state=state,
                            outputs=outputs,
                            records=records,
                            recovery_count=0,
                            step_id=(
                                "__entry_url__"
                            ),
                        )
                    )

                    if self.evidence is not None:
                        self.evidence.record_event(
                            event_type=(
                                "policy_blocked"
                            ),
                            status=(
                                entry_policy
                                .decision
                                .value
                            ),
                            runtime_state_code=(
                                entry_policy.code
                            ),
                            message=(
                                entry_policy.reason
                            ),
                            data={
                                "phase":
                                    "entry_navigation",
                            },
                        )

                        self.evidence.save_result(
                            result
                        )

                    return result

            await self.surface.navigate(
                self.entry_url
            )

            if self.evidence is not None:
                self.evidence.record_event(
                    event_type="navigation_completed",
                    status="completed",
                    url=(
                        self.surface
                        .current_url
                    ),
                )

            for step_index, raw_step in enumerate(artifact.steps):
                step = _bind_step(
                    raw_step,
                    inputs,
                )

                self._validate_step_safety(
                    artifact,
                    step,
                )

                step_started = (
                    time.perf_counter()
                )

                if self.evidence is not None:
                    self.evidence.record_event(
                        event_type="step_started",
                        step_id=step.id,
                        action=(
                            step.action.value
                        ),
                        status="started",
                        url=(
                            self.surface
                            .current_url
                        ),
                        data={
                            "target":
                                (
                                    step
                                    .target
                                    .description
                                    if (
                                        step.target
                                        is not None
                                    )
                                    else None
                                ),
                            "output_name":
                                step.output_name,
                        },
                    )

                try:
                    # ----------------------------------------
                    # Preconditions
                    # ----------------------------------------

                    await self._check_conditions(
                        step.preconditions,
                        outputs,
                        label="Precondition",
                        step_id=step.id,
                    )

                    # ----------------------------------------
                    # Global runtime policy
                    # ----------------------------------------

                    (
                        policy_evaluation,
                        resolved_target,
                    ) = (
                        await self
                        ._evaluate_policy_for_step(
                            step
                        )
                    )

                    if (
                        policy_evaluation
                        is not None
                    ):
                        self._record_policy_evaluation(
                            evaluation=(
                                policy_evaluation
                            ),
                            step_id=step.id,
                            action=step.action,
                        )

                        if (
                            policy_evaluation
                            .decision
                            != PolicyDecision.ALLOW
                        ):
                            state = (
                                self
                                ._policy_runtime_state(
                                    policy_evaluation
                                )
                            )

                            policy_status = (
                                "human_required"
                                if (
                                    policy_evaluation
                                    .decision
                                    == PolicyDecision
                                    .REQUIRE_HUMAN
                                )
                                else "blocked"
                            )

                            records.append(
                                ReplayStepRecord(
                                    step_id=step.id,
                                    action=step.action,
                                    status=(
                                        policy_status
                                    ),
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    output_name=(
                                        step.output_name
                                    ),
                                    message=(
                                        policy_evaluation
                                        .reason
                                    ),
                                )
                            )

                            result = (
                                self
                                ._runtime_terminal_result(
                                    artifact=artifact,
                                    state=state,
                                    outputs=outputs,
                                    records=records,
                                    recovery_count=(
                                        total_recovery_count
                                    ),
                                    step_id=step.id,
                                )
                                .model_copy(
                                    update={
                                        "human_intervention_count":
                                            (
                                                human_intervention_count
                                            ),
                                        "human_resume_attempt_count":
                                            (
                                                human_resume_attempt_count
                                            ),
                                        "human_actions":
                                            (
                                                human_action_records
                                            ),
                                    }
                                )
                            )

                            if self.evidence is not None:
                                event_type = (
                                    "policy_human_required"
                                    if (
                                        policy_evaluation
                                        .decision
                                        == PolicyDecision
                                        .REQUIRE_HUMAN
                                    )
                                    else "policy_blocked"
                                )

                                self.evidence.record_event(
                                    event_type=(
                                        event_type
                                    ),
                                    step_id=step.id,
                                    action=(
                                        step.action.value
                                    ),
                                    status=(
                                        policy_status
                                    ),
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    runtime_state_code=(
                                        policy_evaluation
                                        .code
                                    ),
                                    message=(
                                        policy_evaluation
                                        .reason
                                    ),
                                    data={
                                        "matched_phrase":
                                            (
                                                policy_evaluation
                                                .matched_phrase
                                            ),
                                        "evaluated_live_target":
                                            (
                                                policy_evaluation
                                                .evaluated_live_target
                                            ),
                                    },
                                )

                                await (
                                    self.evidence
                                    .capture_failure(
                                        surface=(
                                            self.surface
                                        ),
                                        step_id=step.id,
                                        reason=(
                                            policy_evaluation
                                            .reason
                                        ),
                                    )
                                )

                                self.evidence.save_result(
                                    result
                                )

                            return result

                    # ----------------------------------------
                    # Deterministic recorded action
                    # ----------------------------------------

                    await self._execute_step(
                        step,
                        outputs,
                        resolved_target=(
                            resolved_target
                        ),
                    )

                    # ----------------------------------------
                    # Post-action URL containment
                    # ----------------------------------------
                    #
                    # A button or form may navigate even when no
                    # href was available before the click. Verify
                    # the browser's actual resulting URL before
                    # replay proceeds.
                    if self.policy is not None:
                        post_url_policy = (
                            self.policy
                            .evaluate_current_url(
                                self.surface
                                .current_url
                            )
                        )

                        self._record_policy_evaluation(
                            evaluation=(
                                post_url_policy
                            ),
                            step_id=step.id,
                            action=step.action,
                        )

                        if (
                            post_url_policy
                            .decision
                            != PolicyDecision.ALLOW
                        ):
                            state = (
                                self
                                ._policy_runtime_state(
                                    post_url_policy
                                )
                            )

                            records.append(
                                ReplayStepRecord(
                                    step_id=step.id,
                                    action=step.action,
                                    status="blocked",
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    output_name=(
                                        step.output_name
                                    ),
                                    message=(
                                        post_url_policy
                                        .reason
                                    ),
                                )
                            )

                            result = (
                                self
                                ._runtime_terminal_result(
                                    artifact=artifact,
                                    state=state,
                                    outputs=outputs,
                                    records=records,
                                    recovery_count=(
                                        total_recovery_count
                                    ),
                                    step_id=step.id,
                                )
                            )

                            if self.evidence is not None:
                                self.evidence.record_event(
                                    event_type=(
                                        "policy_blocked"
                                    ),
                                    step_id=step.id,
                                    action=(
                                        step.action.value
                                    ),
                                    status="blocked",
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    runtime_state_code=(
                                        post_url_policy
                                        .code
                                    ),
                                    message=(
                                        post_url_policy
                                        .reason
                                    ),
                                    data={
                                        "phase":
                                            "post_action_url",
                                    },
                                )

                                await (
                                    self.evidence
                                    .capture_failure(
                                        surface=(
                                            self.surface
                                        ),
                                        step_id=step.id,
                                        reason=(
                                            post_url_policy
                                            .reason
                                        ),
                                    )
                                )

                                self.evidence.save_result(
                                    result
                                )

                            return result

                    # Register newly produced sensitive outputs
                    # before any URL/message/event is persisted.
                    if self.evidence is not None:
                        self.evidence.remember_sensitive_outputs(
                            artifact=artifact,
                            outputs=outputs,
                        )

                    # ----------------------------------------
                    # Runtime state + bounded recovery
                    # ----------------------------------------

                    (
                        runtime_state,
                        recoveries_performed,
                    ) = (
                        await self
                        ._classify_with_recovery(
                            artifact=artifact,
                            outputs=outputs,
                            recovery_attempts=(
                                recovery_attempts
                            ),
                            step_id=step.id,
                        )
                    )

                    total_recovery_count += (
                        recoveries_performed
                    )

                    duration_ms = (
                        (
                            time.perf_counter()
                            - step_started
                        )
                        * 1000.0
                    )

                    # ----------------------------------------
                    # Business outcome
                    # ----------------------------------------

                    if (
                        runtime_state.kind
                        == RuntimeStateKind
                        .BUSINESS_OUTCOME
                    ):
                        record = (
                            ReplayStepRecord(
                                step_id=step.id,
                                action=step.action,
                                status=(
                                    "business_outcome"
                                ),
                                url=(
                                    self.surface
                                    .current_url
                                ),
                                output_name=(
                                    step.output_name
                                ),
                                message=(
                                    runtime_state
                                    .message
                                ),
                            )
                        )

                        records.append(
                            record
                        )

                        result = (
                            self
                            ._runtime_terminal_result(
                                artifact=artifact,
                                state=runtime_state,
                                outputs=outputs,
                                records=records,
                                recovery_count=(
                                    total_recovery_count
                                ),
                                step_id=step.id,
                            )
                        )

                        if self.evidence is not None:
                            self.evidence.record_event(
                                event_type=(
                                    "business_outcome"
                                ),
                                step_id=step.id,
                                action=(
                                    step.action.value
                                ),
                                status=(
                                    "business_outcome"
                                ),
                                url=(
                                    self.surface
                                    .current_url
                                ),
                                duration_ms=(
                                    duration_ms
                                ),
                                runtime_state_code=(
                                    runtime_state
                                    .code
                                ),
                                message=(
                                    runtime_state
                                    .message
                                ),
                            )

                            self.evidence.save_result(
                                result
                            )

                        return result

                    # ----------------------------------------
                    # Human-required state
                    # ----------------------------------------

                    if (
                        runtime_state.kind
                        == RuntimeStateKind
                        .HUMAN_REQUIRED
                    ):
                        if self.handoff is not None:
                            context_artifacts: dict[
                                str,
                                str,
                            ] = {}

                            if self.evidence is not None:
                                context_artifacts = (
                                    await self
                                    .evidence
                                    .capture_failure(
                                        surface=(
                                            self.surface
                                        ),
                                        step_id=step.id,
                                        reason=(
                                            runtime_state
                                            .message
                                        ),
                                    )
                                )

                            intervention_id = (
                                "hitl_"
                                + uuid
                                .uuid4()
                                .hex[:12]
                            )

                            if self.evidence is not None:
                                self.evidence.record_event(
                                    event_type=(
                                        "intervention_requested"
                                    ),
                                    step_id=step.id,
                                    action=(
                                        step.action.value
                                    ),
                                    status="requested",
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    runtime_state_code=(
                                        runtime_state.code
                                    ),
                                    message=(
                                        runtime_state.message
                                    ),
                                    data={
                                        "intervention_id":
                                            intervention_id,
                                        "max_resume_attempts":
                                            (
                                                self
                                                .max_handoff_resume_attempts
                                            ),
                                    },
                                )

                            previous_validation_message: (
                                str | None
                            ) = None

                            human_intervention_count += 1

                            handoff_resolved = False

                            for resume_attempt in range(
                                1,
                                (
                                    self
                                    .max_handoff_resume_attempts
                                    + 1
                                ),
                            ):
                                intervention = (
                                    InterventionRequest(
                                        intervention_id=(
                                            intervention_id
                                        ),
                                        capability_id=(
                                            artifact
                                            .identity
                                            .id
                                        ),
                                        capability_version=(
                                            artifact
                                            .identity
                                            .version
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        reason_code=(
                                            runtime_state.code
                                        ),
                                        reason=(
                                            runtime_state
                                            .message
                                        ),
                                        current_url=(
                                            self.surface
                                            .current_url
                                        ),
                                        evidence_run_id=(
                                            (
                                                self.evidence
                                                .run_id
                                            )
                                            if (
                                                self.evidence
                                                is not None
                                            )
                                            else None
                                        ),
                                        screenshot_path=(
                                            context_artifacts
                                            .get(
                                                "screenshot"
                                            )
                                        ),
                                        resume_attempt=(
                                            resume_attempt
                                        ),
                                        max_resume_attempts=(
                                            self
                                            .max_handoff_resume_attempts
                                        ),
                                        resume_validation_message=(
                                            previous_validation_message
                                        ),
                                    )
                                )

                                if self.evidence is not None:
                                    self.evidence.record_event(
                                        event_type=(
                                            "automation_control_released"
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        status="released",
                                        url=(
                                            self.surface
                                            .current_url
                                        ),
                                        data={
                                            "intervention_id":
                                                intervention_id,
                                            "resume_attempt":
                                                resume_attempt,
                                        },
                                    )

                                    self.evidence.record_event(
                                        event_type=(
                                            "human_control_acquired"
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        status="acquired",
                                        url=(
                                            self.surface
                                            .current_url
                                        ),
                                        data={
                                            "intervention_id":
                                                intervention_id,
                                            "resume_attempt":
                                                resume_attempt,
                                        },
                                    )

                                handoff_result = (
                                    await self
                                    .handoff
                                    .handle(
                                        request=(
                                            intervention
                                        ),
                                        surface=(
                                            self.surface
                                        ),
                                    )
                                )

                                human_resume_attempt_count += 1

                                human_action_records.extend(
                                    handoff_result.actions
                                )

                                if self.evidence is not None:
                                    for human_action in (
                                        handoff_result.actions
                                    ):
                                        self.evidence.record_event(
                                            event_type=(
                                                "human_action"
                                            ),
                                            step_id=step.id,
                                            action=(
                                                human_action
                                                .event_type
                                            ),
                                            status="recorded",
                                            url=(
                                                human_action.url
                                                or (
                                                    self.surface
                                                    .current_url
                                                )
                                            ),
                                            data=(
                                                human_action
                                                .model_dump(
                                                    mode="json"
                                                )
                                            ),
                                        )

                                    self.evidence.record_event(
                                        event_type=(
                                            "human_control_released"
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        status=(
                                            handoff_result
                                            .status
                                            .value
                                        ),
                                        url=(
                                            self.surface
                                            .current_url
                                        ),
                                        message=(
                                            handoff_result
                                            .message
                                        ),
                                        data={
                                            "intervention_id":
                                                intervention_id,
                                            "operator_id":
                                                (
                                                    handoff_result
                                                    .operator_id
                                                ),
                                            "resume_attempt":
                                                resume_attempt,
                                        },
                                    )

                                if (
                                    handoff_result.status
                                    != HandoffStatus
                                    .RESUME_REQUESTED
                                ):
                                    runtime_state = (
                                        RuntimeStateMatch(
                                            kind=(
                                                RuntimeStateKind
                                                .HUMAN_REQUIRED
                                            ),
                                            code=(
                                                "HUMAN_HANDOFF_"
                                                + (
                                                    handoff_result
                                                    .status
                                                    .value
                                                    .upper()
                                                )
                                            ),
                                            message=(
                                                handoff_result
                                                .message
                                            ),
                                        )
                                    )

                                    break

                                if self.evidence is not None:
                                    self.evidence.record_event(
                                        event_type=(
                                            "resume_requested"
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        status="requested",
                                        url=(
                                            self.surface
                                            .current_url
                                        ),
                                        data={
                                            "intervention_id":
                                                intervention_id,
                                            "resume_attempt":
                                                resume_attempt,
                                        },
                                    )

                                    self.evidence.record_event(
                                        event_type=(
                                            "resume_validation_started"
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        status="started",
                                        url=(
                                            self.surface
                                            .current_url
                                        ),
                                        data={
                                            "intervention_id":
                                                intervention_id,
                                            "resume_attempt":
                                                resume_attempt,
                                        },
                                    )

                                (
                                    resume_validation,
                                    post_human_state,
                                    post_human_recoveries,
                                ) = (
                                    await self
                                    ._validate_resume_state(
                                        artifact=artifact,
                                        inputs=inputs,
                                        outputs=outputs,
                                        recovery_attempts=(
                                            recovery_attempts
                                        ),
                                        current_step_index=(
                                            step_index
                                        ),
                                        current_step_id=(
                                            step.id
                                        ),
                                        attempt=(
                                            resume_attempt
                                        ),
                                    )
                                )

                                total_recovery_count += (
                                    post_human_recoveries
                                )

                                if resume_validation.passed:
                                    self.handoff.mark_automation_resumed()

                                    runtime_state = (
                                        post_human_state
                                    )

                                    handoff_resolved = True

                                    if self.evidence is not None:
                                        self.evidence.record_event(
                                            event_type=(
                                                "resume_validation_passed"
                                            ),
                                            step_id=step.id,
                                            action=(
                                                step.action.value
                                            ),
                                            status="passed",
                                            url=(
                                                self.surface
                                                .current_url
                                            ),
                                            runtime_state_code=(
                                                post_human_state
                                                .code
                                            ),
                                            message=(
                                                resume_validation
                                                .message
                                            ),
                                            data={
                                                "intervention_id":
                                                    intervention_id,
                                                "resume_attempt":
                                                    resume_attempt,
                                                "next_step_id":
                                                    (
                                                        resume_validation
                                                        .next_step_id
                                                    ),
                                                "next_target":
                                                    (
                                                        resume_validation
                                                        .next_target_description
                                                    ),
                                            },
                                        )

                                        self.evidence.record_event(
                                            event_type=(
                                                "automation_control_resumed"
                                            ),
                                            step_id=step.id,
                                            action=(
                                                step.action.value
                                            ),
                                            status="resumed",
                                            url=(
                                                self.surface
                                                .current_url
                                            ),
                                            data={
                                                "intervention_id":
                                                    intervention_id,
                                                "resume_attempt":
                                                    resume_attempt,
                                            },
                                        )

                                        self.evidence.record_event(
                                            event_type=(
                                                "intervention_resolved"
                                            ),
                                            step_id=step.id,
                                            action=(
                                                step.action.value
                                            ),
                                            status="resolved",
                                            url=(
                                                self.surface
                                                .current_url
                                            ),
                                            data={
                                                "intervention_id":
                                                    intervention_id,
                                            },
                                        )

                                    break

                                self.handoff.mark_resume_rejected()

                                previous_validation_message = (
                                    resume_validation.message
                                )

                                if self.evidence is not None:
                                    self.evidence.record_event(
                                        event_type=(
                                            "resume_validation_failed"
                                        ),
                                        step_id=step.id,
                                        action=(
                                            step.action.value
                                        ),
                                        status="failed",
                                        url=(
                                            self.surface
                                            .current_url
                                        ),
                                        runtime_state_code=(
                                            resume_validation
                                            .runtime_state_code
                                        ),
                                        message=(
                                            resume_validation
                                            .message
                                        ),
                                        data={
                                            "intervention_id":
                                                intervention_id,
                                            "resume_attempt":
                                                resume_attempt,
                                            "next_step_id":
                                                (
                                                    resume_validation
                                                    .next_step_id
                                                ),
                                            "next_target":
                                                (
                                                    resume_validation
                                                    .next_target_description
                                                ),
                                            "control_owner":
                                                "human",
                                        },
                                    )

                                if (
                                    resume_attempt
                                    >= (
                                        self
                                        .max_handoff_resume_attempts
                                    )
                                ):
                                    runtime_state = (
                                        RuntimeStateMatch(
                                            kind=(
                                                RuntimeStateKind
                                                .HUMAN_REQUIRED
                                            ),
                                            code=(
                                                "HUMAN_RESUME_STATE_INVALID"
                                            ),
                                            message=(
                                                "Human resume "
                                                "validation failed "
                                                f"after "
                                                f"{resume_attempt} "
                                                "attempt(s). "
                                                + (
                                                    resume_validation
                                                    .message
                                                )
                                            ),
                                            matched_text=(
                                                resume_validation
                                                .next_target_description
                                            ),
                                        )
                                    )

                                    break

                            if handoff_resolved:
                                # Resume validation passed. The
                                # current step may now finish and
                                # replay continues to the next
                                # recorded step.
                                pass

                        if (
                            runtime_state.kind
                            == RuntimeStateKind
                            .HUMAN_REQUIRED
                        ):
                            record = (
                                ReplayStepRecord(
                                    step_id=step.id,
                                    action=step.action,
                                    status=(
                                        "human_required"
                                    ),
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    output_name=(
                                        step.output_name
                                    ),
                                    message=(
                                        runtime_state
                                        .message
                                    ),
                                )
                            )

                            records.append(
                                record
                            )

                            result = (
                                self
                                ._runtime_terminal_result(
                                    artifact=artifact,
                                    state=runtime_state,
                                    outputs=outputs,
                                    records=records,
                                    recovery_count=(
                                        total_recovery_count
                                    ),
                                    step_id=step.id,
                                )
                                .model_copy(
                                    update={
                                        "human_intervention_count":
                                            human_intervention_count,
                                        "human_resume_attempt_count":
                                            human_resume_attempt_count,
                                        "human_actions":
                                            human_action_records,
                                    }
                                )
                            )

                            if self.evidence is not None:
                                self.evidence.record_event(
                                    event_type=(
                                        "human_required"
                                    ),
                                    step_id=step.id,
                                    action=(
                                        step.action.value
                                    ),
                                    status=(
                                        "human_required"
                                    ),
                                    url=(
                                        self.surface
                                        .current_url
                                    ),
                                    runtime_state_code=(
                                        runtime_state.code
                                    ),
                                    message=(
                                        runtime_state.message
                                    ),
                                )

                                if self.handoff is None:
                                    await (
                                        self.evidence
                                        .capture_failure(
                                            surface=(
                                                self.surface
                                            ),
                                            step_id=step.id,
                                            reason=(
                                                runtime_state
                                                .message
                                            ),
                                        )
                                    )

                                self.evidence.save_result(
                                    result
                                )

                            return result

                    # ----------------------------------------
                    # Hard failure
                    # ----------------------------------------

                    if (
                        runtime_state.kind
                        == RuntimeStateKind
                        .HARD_FAILURE
                    ):
                        record = (
                            ReplayStepRecord(
                                step_id=step.id,
                                action=step.action,
                                status="failed",
                                url=(
                                    self.surface
                                    .current_url
                                ),
                                output_name=(
                                    step.output_name
                                ),
                                message=(
                                    runtime_state
                                    .message
                                ),
                            )
                        )

                        records.append(
                            record
                        )

                        result = (
                            self
                            ._runtime_terminal_result(
                                artifact=artifact,
                                state=runtime_state,
                                outputs=outputs,
                                records=records,
                                recovery_count=(
                                    total_recovery_count
                                ),
                                step_id=step.id,
                            )
                        )

                        if self.evidence is not None:
                            self.evidence.record_event(
                                event_type=(
                                    "runtime_failure"
                                ),
                                step_id=step.id,
                                action=(
                                    step.action.value
                                ),
                                status="failed",
                                url=(
                                    self.surface
                                    .current_url
                                ),
                                duration_ms=(
                                    duration_ms
                                ),
                                runtime_state_code=(
                                    runtime_state
                                    .code
                                ),
                                message=(
                                    runtime_state
                                    .message
                                ),
                            )

                            await (
                                self.evidence
                                .capture_failure(
                                    surface=(
                                        self.surface
                                    ),
                                    step_id=step.id,
                                    reason=(
                                        runtime_state
                                        .message
                                    ),
                                )
                            )

                            self.evidence.save_result(
                                result
                            )

                        return result

                    # ----------------------------------------
                    # Recovery attempts exhausted
                    # ----------------------------------------

                    if (
                        runtime_state.kind
                        == RuntimeStateKind
                        .RECOVERABLE
                    ):
                        message = (
                            "Recoverable condition "
                            f"'{runtime_state.code}' "
                            "remained after maximum "
                            "recovery attempts."
                        )

                        record = (
                            ReplayStepRecord(
                                step_id=step.id,
                                action=step.action,
                                status="failed",
                                url=(
                                    self.surface
                                    .current_url
                                ),
                                output_name=(
                                    step.output_name
                                ),
                                message=message,
                            )
                        )

                        records.append(
                            record
                        )

                        result = (
                            self
                            ._runtime_terminal_result(
                                artifact=artifact,
                                state=runtime_state,
                                outputs=outputs,
                                records=records,
                                recovery_count=(
                                    total_recovery_count
                                ),
                                step_id=step.id,
                            )
                        )

                        if self.evidence is not None:
                            self.evidence.record_event(
                                event_type=(
                                    "recovery_exhausted"
                                ),
                                step_id=step.id,
                                action=(
                                    step.action.value
                                ),
                                status="failed",
                                url=(
                                    self.surface
                                    .current_url
                                ),
                                duration_ms=(
                                    duration_ms
                                ),
                                runtime_state_code=(
                                    runtime_state
                                    .code
                                ),
                                recovery_action=(
                                    runtime_state
                                    .recovery_action
                                ),
                                recovery_attempt=(
                                    runtime_state
                                    .recovery_attempt
                                ),
                                message=message,
                            )

                            await (
                                self.evidence
                                .capture_failure(
                                    surface=(
                                        self.surface
                                    ),
                                    step_id=step.id,
                                    reason=message,
                                )
                            )

                            self.evidence.save_result(
                                result
                            )

                        return result

                    # NORMAL: enforce recorded postconditions.
                    await self._check_conditions(
                        step.postconditions,
                        outputs,
                        label="Postcondition",
                        step_id=step.id,
                    )

                except Exception as exc:
                    duration_ms = (
                        (
                            time.perf_counter()
                            - step_started
                        )
                        * 1000.0
                    )

                    records.append(
                        ReplayStepRecord(
                            step_id=step.id,
                            action=step.action,
                            status="failed",
                            url=(
                                self.surface
                                .current_url
                            ),
                            output_name=(
                                step.output_name
                            ),
                            message=str(
                                exc
                            ),
                        )
                    )

                    if self.evidence is not None:
                        self.evidence.record_event(
                            event_type=(
                                "step_exception"
                            ),
                            step_id=step.id,
                            action=(
                                step.action.value
                            ),
                            status="failed",
                            url=(
                                self.surface
                                .current_url
                            ),
                            duration_ms=(
                                duration_ms
                            ),
                            message=str(
                                exc
                            ),
                        )

                        await (
                            self.evidence
                            .capture_failure(
                                surface=(
                                    self.surface
                                ),
                                step_id=step.id,
                                reason=str(
                                    exc
                                ),
                            )
                        )

                        self.evidence.save_exception(
                            exc=exc,
                            step_id=step.id,
                            url=(
                                self.surface
                                .current_url
                            ),
                        )

                    raise

                duration_ms = (
                    (
                        time.perf_counter()
                        - step_started
                    )
                    * 1000.0
                )

                records.append(
                    ReplayStepRecord(
                        step_id=step.id,
                        action=step.action,
                        status="completed",
                        url=(
                            self.surface
                            .current_url
                        ),
                        output_name=(
                            step.output_name
                        ),
                        message=(
                            (
                                f"Completed after "
                                f"{recoveries_performed} "
                                "recovery action(s)."
                            )
                            if recoveries_performed
                            else None
                        ),
                    )
                )

                if self.evidence is not None:
                    self.evidence.record_event(
                        event_type=(
                            "step_completed"
                        ),
                        step_id=step.id,
                        action=(
                            step.action.value
                        ),
                        status="completed",
                        url=(
                            self.surface
                            .current_url
                        ),
                        duration_ms=(
                            duration_ms
                        ),
                        data={
                            "recoveries_performed":
                                recoveries_performed,
                            "output_name":
                                step.output_name,
                        },
                    )

            # --------------------------------------------
            # Final capability checkpoint
            # --------------------------------------------

            checkpoint = _bind_condition(
                artifact.checkpoint,
                inputs,
            )

            checkpoint_passed = (
                await self
                .surface
                .check_condition(
                    checkpoint,
                    outputs,
                )
            )

            if not checkpoint_passed:
                exc = ReplayCheckpointError(
                    (
                        "Capability checkpoint "
                        "did not pass."
                    )
                )

                if self.evidence is not None:
                    self.evidence.record_event(
                        event_type=(
                            "checkpoint_failed"
                        ),
                        status="failed",
                        url=(
                            self.surface
                            .current_url
                        ),
                        message=str(
                            exc
                        ),
                    )

                    await (
                        self.evidence
                        .capture_failure(
                            surface=(
                                self.surface
                            ),
                            step_id=None,
                            reason=str(
                                exc
                            ),
                        )
                    )

                    self.evidence.save_exception(
                        exc=exc,
                        step_id=None,
                        url=(
                            self.surface
                            .current_url
                        ),
                    )

                raise exc

            if self.evidence is not None:
                self.evidence.record_event(
                    event_type=(
                        "checkpoint_passed"
                    ),
                    status="completed",
                    url=(
                        self.surface
                        .current_url
                    ),
                )

            result = ReplayResult(
                capability_id=(
                    artifact.identity.id
                ),
                capability_version=(
                    artifact.identity.version
                ),
                status=ReplayStatus.COMPLETED,
                outputs=outputs,
                steps=records,
                checkpoint_passed=True,
                runtime_state=None,
                recovery_count=(
                    total_recovery_count
                ),
                human_intervention_count=(
                    human_intervention_count
                ),
                human_resume_attempt_count=(
                    human_resume_attempt_count
                ),
                human_actions=(
                    human_action_records
                ),
                failed_step_id=None,
                message=(
                    "Capability replay "
                    "completed successfully."
                ),
            )

            if self.evidence is not None:
                self.evidence.save_result(
                    result
                )

            return result

        except Exception:
            # Per-step and checkpoint branches already capture
            # rich evidence. This outer boundary only preserves
            # the original exception semantics.
            raise
