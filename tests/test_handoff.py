from __future__ import annotations

from cua.handoff import (
    ControlOwner,
    ControlState,
    HandoffResult,
    HandoffStatus,
    HumanActionRecord,
    InterventionRequest,
    ResumeValidationResult,
)
from cua.playwright_handoff import (
    PlaywrightHumanHandoff,
)


def test_intervention_request_contract():
    request = InterventionRequest(
        intervention_id="hitl_test",
        capability_id=(
            "lookup_savings_balance"
        ),
        capability_version="1.0.0",
        step_id=(
            "step_03_click_savings_link"
        ),
        action="click",
        reason_code=(
            "SECURITY_VERIFICATION"
        ),
        reason=(
            "Security verification "
            "requires a human."
        ),
        current_url=(
            "http://127.0.0.1:8000/"
            "legacy/member/"
            "[REDACTED]/account/savings"
        ),
        resume_attempt=1,
        max_resume_attempts=3,
    )

    assert (
        request.requested_owner
        == ControlOwner.HUMAN
    )

    assert (
        request.resume_attempt
        == 1
    )

    assert (
        request.max_resume_attempts
        == 3
    )


def test_handoff_result_is_resume_request_not_automatic_resume():
    result = HandoffResult(
        intervention_id="hitl_test",
        status=(
            HandoffStatus
            .RESUME_REQUESTED
        ),
        operator_id="operator-1",
        actions=[],
        message=(
            "Validate before resuming."
        ),
    )

    assert (
        result.status
        == HandoffStatus
        .RESUME_REQUESTED
    )

    assert (
        result.status.value
        == "resume_requested"
    )


def test_resume_validation_contract():
    result = (
        ResumeValidationResult(
            passed=False,
            attempt=1,
            message=(
                "Expected continuation "
                "target missing."
            ),
            current_url=(
                "http://127.0.0.1:8000/"
                "legacy/member/"
                "[REDACTED]"
            ),
            next_step_id="step_04",
            next_target_description=(
                "Current Balance value"
            ),
            runtime_state_code=(
                "NORMAL"
            ),
        )
    )

    assert result.passed is False

    assert (
        result.next_step_id
        == "step_04"
    )


def test_control_state_machine_values_are_explicit():
    assert (
        ControlState.AUTOMATION.value
        == "automation"
    )

    assert (
        ControlState
        .WAITING_FOR_HUMAN
        .value
        == "waiting_for_human"
    )

    assert (
        ControlState.HUMAN.value
        == "human"
    )

    assert (
        ControlState
        .VALIDATING_RESUME
        .value
        == "validating_resume"
    )


def test_handler_only_returns_automation_owner_after_validation():
    handler = (
        PlaywrightHumanHandoff()
    )

    assert (
        handler.state
        == ControlState.AUTOMATION
    )

    assert (
        handler.owner
        == ControlOwner.AUTOMATION
    )

    # Simulate the state reached after a human has requested
    # resume. Validation has not passed yet.
    handler._state = (
        ControlState
        .VALIDATING_RESUME
    )

    assert (
        handler.owner
        == ControlOwner.HUMAN
    )

    handler.mark_automation_resumed()

    assert (
        handler.state
        == ControlState.AUTOMATION
    )

    assert (
        handler.owner
        == ControlOwner.AUTOMATION
    )


def test_human_action_contract():
    action = HumanActionRecord(
        timestamp=(
            "2026-08-18T12:00:00+00:00"
        ),
        event_type="click",
        tag="button",
        text=(
            "Acknowledge & Continue"
        ),
    )

    assert (
        action.event_type
        == "click"
    )