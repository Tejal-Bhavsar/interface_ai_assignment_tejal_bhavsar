from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from cua.surface import ComputerSurface


class ControlOwner(str, Enum):
    """
    Who currently owns the live session.
    """

    AUTOMATION = "automation"
    HUMAN = "human"


class ControlState(str, Enum):
    """
    Explicit handoff state machine.

    AUTOMATION
        Automation owns the live session.

    WAITING_FOR_HUMAN
        Automation has paused and an intervention is being
        routed.

    HUMAN
        A human operator owns the live session.

    VALIDATING_RESUME
        The human requested resume, but automation has not yet
        accepted control. The current live state must first
        satisfy deterministic resume validation.
    """

    AUTOMATION = "automation"
    WAITING_FOR_HUMAN = (
        "waiting_for_human"
    )
    HUMAN = "human"
    VALIDATING_RESUME = (
        "validating_resume"
    )


class HandoffStatus(str, Enum):
    """
    Result of one human-control cycle.

    RESUME_REQUESTED means:
        The operator is done and wants automation to validate
        whether it is safe to resume.

    It does NOT mean automation has already resumed.
    """

    RESUME_REQUESTED = (
        "resume_requested"
    )

    # Backwards-compatible alias for the previous Step 14 API.
    RESUMED = "resume_requested"

    CANCELLED = "cancelled"
    FAILED = "failed"


class HumanActionRecord(BaseModel):
    """
    One sanitized human action observed while the operator
    owned the live browser session.
    """

    timestamp: str
    event_type: str

    tag: str | None = None
    role: str | None = None

    accessible_name: (
        str | None
    ) = None

    text: str | None = None
    href: str | None = None
    value: str | None = None
    url: str | None = None


class InterventionRequest(BaseModel):
    """
    Context routed from replay to a human operator.

    This deliberately carries semantic context rather than raw
    PII or a raw DOM dump.
    """

    intervention_id: str

    capability_id: str
    capability_version: str

    step_id: str
    action: str

    reason_code: str
    reason: str

    current_url: str

    evidence_run_id: (
        str | None
    ) = None

    screenshot_path: (
        str | None
    ) = None

    requested_owner: ControlOwner = (
        ControlOwner.HUMAN
    )

    resume_attempt: int = 1
    max_resume_attempts: int = 3

    resume_validation_message: (
        str | None
    ) = None


class ResumeValidationResult(
    BaseModel
):
    """
    Deterministic validation performed after a human requests
    resume but before automation takes control again.
    """

    passed: bool

    attempt: int

    message: str

    current_url: str

    next_step_id: (
        str | None
    ) = None

    next_target_description: (
        str | None
    ) = None

    runtime_state_code: (
        str | None
    ) = None


class HandoffResult(BaseModel):
    """
    Result returned by one human-control cycle.

    A RESUME_REQUESTED result means the human released control
    and replay must validate the live state before accepting
    automation ownership.
    """

    intervention_id: str

    status: HandoffStatus

    operator_id: str

    actions: list[
        HumanActionRecord
    ] = Field(
        default_factory=list
    )

    message: str

    final_url: str | None = None


class HumanHandoffHandler(Protocol):
    """
    Surface-independent handoff seam used by ReplayEngine.
    """

    @property
    def owner(
        self,
    ) -> ControlOwner:
        ...

    @property
    def state(
        self,
    ) -> ControlState:
        ...

    async def handle(
        self,
        *,
        request: InterventionRequest,
        surface: ComputerSurface,
    ) -> HandoffResult:
        ...

    def mark_automation_resumed(
        self,
    ) -> None:
        """
        Called only after deterministic resume validation passes.
        """
        ...

    def mark_resume_rejected(
        self,
    ) -> None:
        """
        Called when resume validation fails and control should
        return to the human.
        """
        ...