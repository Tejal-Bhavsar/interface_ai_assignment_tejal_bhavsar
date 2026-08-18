from cua.replay import (
    ReplayResult,
    ReplayStatus,
    RuntimeStateKind,
    RuntimeStateMatch,
    RuntimeClassifier,
    ReplayEngine,
)

import pytest

from cua.models import (
    Condition,
    ConditionType,
    FailureRule,
    OutcomeRule,
    RecoveryRule,
)

from pathlib import Path

from cua.compiler import (
    load_capability_artifact,
)


def make_artifact_for_runtime_tests():

    path = (
        Path(__file__)
        .resolve()
        .parents[1]
        / "capabilities"
        / "lookup_savings_balance.v1.json"
    )

    return load_capability_artifact(
        path
    )


class FakeConditionSurface:
    """
    Minimal surface-like object for RuntimeClassifier tests.

    A condition matches when its text exists in visible_text.
    """

    def __init__(
        self,
        visible_text: str,
    ):
        self.visible_text = (
            visible_text
        )

    async def check_condition(
        self,
        condition,
        outputs=None,
    ):
        if (
            condition.type
            == ConditionType.TEXT_PRESENT
        ):
            return (
                condition.value
                in self.visible_text
            )

        return False

def test_success_result_contract():

    result = ReplayResult(
        capability_id=(
            "lookup_savings_balance"
        ),

        capability_version=(
            "1.0.0"
        ),

        status=(
            ReplayStatus.COMPLETED
        ),

        outputs={
            "current_savings_balance":
                "$6,320.40",
        },

        checkpoint_passed=True,

        message=(
            "Capability replay "
            "completed successfully."
        ),
    )

    assert (
        result.status
        == ReplayStatus.COMPLETED
    )

    assert (
        result.runtime_state
        is None
    )

    assert (
        result.checkpoint_passed
        is True
    )


def test_business_outcome_result_contract():

    state = RuntimeStateMatch(
        kind=(
            RuntimeStateKind
            .BUSINESS_OUTCOME
        ),

        code="MEMBER_NOT_FOUND",

        message=(
            "No member matched "
            "the supplied identifier."
        ),

        matched_text=(
            "Member not found"
        ),
    )

    result = ReplayResult(
        capability_id=(
            "lookup_savings_balance"
        ),

        capability_version=(
            "1.0.0"
        ),

        status=(
            ReplayStatus
            .BUSINESS_OUTCOME
        ),

        runtime_state=state,

        failed_step_id=(
            "step_02_click_search_button"
        ),

        message=(
            "Replay ended with a "
            "known business outcome."
        ),
    )

    assert (
        result.status
        == ReplayStatus
        .BUSINESS_OUTCOME
    )

    assert (
        result.runtime_state
        is not None
    )

    assert (
        result.runtime_state.code
        == "MEMBER_NOT_FOUND"
    )


def test_recoverable_runtime_state_contract():

    state = RuntimeStateMatch(
        kind=(
            RuntimeStateKind
            .RECOVERABLE
        ),

        code="SESSION_EXPIRED",

        message=(
            "Session expired."
        ),

        matched_text=(
            "Session expired"
        ),

        recovery_action="reload",

        recovery_attempt=1,
    )

    assert (
        state.kind
        == RuntimeStateKind
        .RECOVERABLE
    )

    assert (
        state.recovery_action
        == "reload"
    )

    assert (
        state.recovery_attempt
        == 1
    )


def test_hard_failure_result_contract():

    state = RuntimeStateMatch(
        kind=(
            RuntimeStateKind
            .HARD_FAILURE
        ),

        code="PERMISSION_DENIED",

        message=(
            "Operator does not have "
            "permission."
        ),

        matched_text=(
            "Permission denied"
        ),
    )

    result = ReplayResult(
        capability_id=(
            "lookup_savings_balance"
        ),

        capability_version=(
            "1.0.0"
        ),

        status=(
            ReplayStatus.FAILED
        ),

        runtime_state=state,

        failed_step_id=(
            "step_02_click_search_button"
        ),

        message=(
            "Replay stopped due to "
            "a hard application failure."
        ),
    )

    assert (
        result.status
        == ReplayStatus.FAILED
    )

    assert (
        result.runtime_state.code
        == "PERMISSION_DENIED"
    )



@pytest.mark.asyncio
async def test_classifier_detects_business_outcome():

    surface = FakeConditionSurface(
        "Member not found"
    )

    classifier = RuntimeClassifier(
        surface=surface
    )

    artifact = (
        make_artifact_for_runtime_tests()
    )

    result = await classifier.classify(
        artifact=artifact,
        outputs={},
    )

    assert (
        result.kind
        == RuntimeStateKind
        .BUSINESS_OUTCOME
    )

    assert (
        result.code
        == "MEMBER_NOT_FOUND"
    )

@pytest.mark.asyncio
async def test_classifier_detects_recoverable_state():

    surface = FakeConditionSurface(
        "Session expired"
    )

    classifier = RuntimeClassifier(
        surface=surface
    )

    artifact = (
        make_artifact_for_runtime_tests()
    )

    result = await classifier.classify(
        artifact=artifact,
        outputs={},
    )

    assert (
        result.kind
        == RuntimeStateKind
        .RECOVERABLE
    )

    assert (
        result.code
        == "SESSION_EXPIRED"
    )

@pytest.mark.asyncio
async def test_classifier_detects_hard_failure():

    surface = FakeConditionSurface(
        "Permission denied"
    )

    classifier = RuntimeClassifier(
        surface=surface
    )

    artifact = (
        make_artifact_for_runtime_tests()
    )

    result = await classifier.classify(
        artifact=artifact,
        outputs={},
    )

    assert (
        result.kind
        == RuntimeStateKind
        .HARD_FAILURE
    )

    assert (
        result.code
        == "PERMISSION_DENIED"
    )

@pytest.mark.asyncio
async def test_classifier_returns_normal():

    surface = FakeConditionSurface(
        (
            "Member Details "
            "Accounts Savings"
        )
    )

    classifier = RuntimeClassifier(
        surface=surface
    )

    artifact = (
        make_artifact_for_runtime_tests()
    )

    result = await classifier.classify(
        artifact=artifact,
        outputs={},
    )

    assert (
        result.kind
        == RuntimeStateKind.NORMAL
    )

    assert (
        result.code
        == "NORMAL"
    )

def test_replay_engine_keeps_surface():

    surface = FakeConditionSurface(
        "Member Search"
    )

    engine = ReplayEngine(
        surface=surface,
        entry_url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),
        allow_draft=True,
    )

    assert (
        engine.surface
        is surface
    )

    assert (
        engine.runtime_classifier
        .surface
        is surface
    )

    assert (
        engine.entry_url
        == (
            "http://127.0.0.1:8000"
            "/legacy"
        )
    )
