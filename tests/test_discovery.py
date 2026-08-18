from collections.abc import (
    Mapping,
)
from pathlib import Path
from typing import Any

import pytest

from cua.discovery import (
    DiscoveryEngine,
)

from cua.llm.mock_provider import (
    MockActionProvider,
)

from cua.models import (
    ActionType,
    AgentAction,
    Condition,
    ConditionType,
    DiscoveryStatus,
    LocatorCandidate,
    LocatorKind,
    Observation,
    PolicyDecision,
    ResolvedTargetInfo,
    RiskLevel,
    TargetDescriptor,
)

from cua.policy import (
    PolicyEvaluation,
)

from cua.surface import (
    ComputerSurface,
    ResolvedTarget,
    TargetNotFoundError,
)


def target(
    description: str,
) -> TargetDescriptor:

    return TargetDescriptor(
        description=description,

        locators=[
            LocatorCandidate(
                kind=LocatorKind.TEXT,
                value=description,
            )
        ],
    )


class FakeSurface(
    ComputerSurface
):

    def __init__(
        self,
        *,
        extract_value: str = (
            "$8,421.22"
        ),
        fail_resolution: bool = False,
        condition_result: bool = True,
    ):
        self.started = False

        self.closed = False

        self._url = ""

        self.extract_value = (
            extract_value
        )

        self.fail_resolution = (
            fail_resolution
        )

        self.condition_result = (
            condition_result
        )

        self.calls: list[str] = []

    @property
    def surface_type(
        self,
    ) -> str:
        return "fake"

    @property
    def current_url(
        self,
    ) -> str:
        return self._url

    async def start(
        self,
    ) -> None:
        self.started = True

    async def close(
        self,
    ) -> None:
        self.closed = True

    async def navigate(
        self,
        url: str,
    ) -> None:
        self.calls.append(
            f"navigate:{url}"
        )

        self._url = url

    async def reload(
        self,
    ) -> None:
        self.calls.append(
            "reload"
        )

    async def observe(
        self,
    ) -> Observation:

        return Observation(
            url=self._url,
            title="Fake LegacyCore",
            visible_text=(
                "Member ID Search "
                "Savings Current Balance"
            ),
            controls=[],
        )

    async def resolve_target(
        self,
        descriptor: TargetDescriptor,
    ) -> ResolvedTarget:

        if self.fail_resolution:
            raise TargetNotFoundError(
                descriptor
            )

        candidate = (
            descriptor.locators[0]
        )

        return ResolvedTarget(
            descriptor=descriptor,
            candidate=candidate,
            candidate_index=0,

            info=ResolvedTargetInfo(
                tag="button",
                role="button",
                text=(
                    descriptor.description
                ),
                name=(
                    descriptor.description
                ),
            ),

            backend_ref=(
                descriptor.description
            ),
        )

    async def click(
        self,
        resolved: ResolvedTarget,
    ) -> None:

        description = (
            resolved
            .descriptor
            .description
        )

        self.calls.append(
            f"click:{description}"
        )

        if (
            description
            == "Search button"
        ):
            self._url = (
                "http://127.0.0.1:8000"
                "/legacy/member/1001"
            )

    async def fill(
        self,
        resolved: ResolvedTarget,
        value: str,
    ) -> None:

        self.calls.append(
            (
                f"fill:"
                f"{resolved.descriptor.description}"
                f":{value}"
            )
        )

    async def select(
        self,
        resolved: ResolvedTarget,
        value: str,
    ) -> None:

        self.calls.append(
            (
                f"select:"
                f"{resolved.descriptor.description}"
                f":{value}"
            )
        )

    async def extract_text(
        self,
        resolved: ResolvedTarget,
    ) -> str:

        self.calls.append(
            (
                f"extract:"
                f"{resolved.descriptor.description}"
            )
        )

        return self.extract_value

    async def wait(
        self,
        milliseconds: int,
    ) -> None:

        self.calls.append(
            f"wait:{milliseconds}"
        )

    async def check_condition(
        self,
        condition: Condition,
        outputs: Mapping[
            str,
            Any,
        ] | None = None,
    ) -> bool:

        return self.condition_result

    async def capture_screenshot(
        self,
        path: Path,
        *,
        mask_sensitive: bool = True,
    ) -> Path:

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(
            b"fake screenshot"
        )

        return path

    async def structure_snapshot(
        self,
    ) -> str | None:

        return (
            "<html>fake</html>"
        )


class FakePolicy:
    """
    Test double matching the current PolicyEngine interface.

    It lets discovery tests independently control:
      - URL/navigation decisions
      - action decisions
    """

    def __init__(
        self,
        *,
        url_decision=(
            PolicyDecision.ALLOW
        ),
        action_decision=(
            PolicyDecision.ALLOW
        ),
    ):
        self.url_decision = (
            url_decision
        )

        self.action_decision = (
            action_decision
        )

    @staticmethod
    def _evaluation(
        decision: PolicyDecision,
        *,
        code: str,
        reason: str,
    ):
        return PolicyEvaluation(
            decision=decision,
            code=code,
            reason=reason,
        )

    def evaluate_navigation(
        self,
        url: str,
    ):
        return self._evaluation(
            self.url_decision,
            code=(
                "FAKE_URL_POLICY"
            ),
            reason=(
                "Fake navigation "
                "policy decision."
            ),
        )

    def evaluate_current_url(
        self,
        url: str,
    ):
        return self._evaluation(
            self.url_decision,
            code=(
                "FAKE_URL_POLICY"
            ),
            reason=(
                "Fake current URL "
                "policy decision."
            ),
        )

    def evaluate_action(
        self,
        *,
        action,
        current_url: str,
        risk_level=None,
        target_description=None,
        resolved_info=None,
        destination_url=None,
    ):
        return self._evaluation(
            self.action_decision,
            code=(
                "FAKE_ACTION_POLICY"
            ),
            reason=(
                "Fake action "
                "policy decision."
            ),
        )


@pytest.mark.asyncio
async def test_discovery_full_scripted_flow():

    surface = FakeSurface()

    actions = [
        AgentAction(
            action=ActionType.FILL,

            target=target(
                "Member ID input"
            ),

            value="1001",

            reason=(
                "Enter member ID."
            ),

            risk_hint=RiskLevel.SAFE,
        ),

        AgentAction(
            action=ActionType.CLICK,

            target=target(
                "Search button"
            ),

            reason="Search member.",

            risk_hint=RiskLevel.SAFE,
        ),

        AgentAction(
            action=(
                ActionType.EXTRACT
            ),

            target=target(
                "Current Balance"
            ),

            output_name=(
                "savings_balance"
            ),

            reason=(
                "Read savings balance."
            ),

            risk_hint=RiskLevel.SAFE,
        ),

        AgentAction(
            action=(
                ActionType.COMPLETE
            ),

            reason=(
                "Requested balance "
                "has been extracted."
            ),

            risk_hint=RiskLevel.SAFE,
        ),
    ]

    provider = MockActionProvider(
        actions=actions
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        # FakePolicy intentionally uses
        # the same interface.
        policy=FakePolicy(),  # type: ignore[arg-type]

        max_steps=10,
    )

    async with surface:

        result = await engine.run(
            goal=(
                "Look up member 1001 "
                "and return savings "
                "balance."
            ),

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == DiscoveryStatus.COMPLETED
    )

    assert (
        result.outputs[
            "savings_balance"
        ]
        == "$8,421.22"
    )

    assert len(
        result.steps
    ) == 4

    assert (
        "fill:Member ID input:1001"
        in surface.calls
    )

    assert (
        "click:Search button"
        in surface.calls
    )

    assert (
        "extract:Current Balance"
        in surface.calls
    )


@pytest.mark.asyncio
async def test_policy_block_prevents_execution():

    surface = FakeSurface()

    provider = MockActionProvider(
        actions=[
            AgentAction(
                action=(
                    ActionType.CLICK
                ),

                target=target(
                    "Dangerous button"
                ),

                reason="Click.",

                risk_hint=(
                    RiskLevel.SAFE
                ),
            )
        ]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(
            action_decision=(
                PolicyDecision.BLOCK
            )
        ),  # type: ignore[arg-type]
    )

    async with surface:

        result = await engine.run(
            goal="Test block.",

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == (
            DiscoveryStatus
            .POLICY_BLOCKED
        )
    )

    assert (
        "click:Dangerous button"
        not in surface.calls
    )


@pytest.mark.asyncio
async def test_policy_human_requirement_stops():

    surface = FakeSurface()

    provider = MockActionProvider(
        actions=[
            AgentAction(
                action=(
                    ActionType.CLICK
                ),

                target=target(
                    (
                        "Confirm Open "
                        "Sub-Account"
                    )
                ),

                reason="Confirm.",

                risk_hint=(
                    RiskLevel.RISKY
                ),
            )
        ]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(
            action_decision=(
                PolicyDecision
                .REQUIRE_HUMAN
            )
        ),  # type: ignore[arg-type]
    )

    async with surface:

        result = await engine.run(
            goal="Open sub-account.",

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == (
            DiscoveryStatus
            .INTERVENTION_REQUIRED
        )
    )

    assert not any(
        item.startswith(
            "click:"
        )
        for item in surface.calls
    )


@pytest.mark.asyncio
async def test_model_request_human_stops():

    surface = FakeSurface()

    provider = MockActionProvider(
        actions=[
            AgentAction(
                action=(
                    ActionType
                    .REQUEST_HUMAN
                ),

                reason=(
                    "Security verification "
                    "is required."
                ),

                risk_hint=(
                    RiskLevel.RISKY
                ),
            )
        ]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(),  # type: ignore[arg-type]
    )

    async with surface:

        result = await engine.run(
            goal="Test.",

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == (
            DiscoveryStatus
            .INTERVENTION_REQUIRED
        )
    )


@pytest.mark.asyncio
async def test_initial_url_policy_block():

    surface = FakeSurface()

    provider = MockActionProvider(
        actions=[]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(
            url_decision=(
                PolicyDecision.BLOCK
            )
        ),  # type: ignore[arg-type]
    )

    async with surface:

        result = await engine.run(
            goal="Test.",

            entry_url=(
                "https://evil.example.com"
            ),
        )

    assert (
        result.status
        == (
            DiscoveryStatus
            .POLICY_BLOCKED
        )
    )

    assert not any(
        item.startswith(
            "navigate:"
        )
        for item in surface.calls
    )


@pytest.mark.asyncio
async def test_discovery_max_steps():

    surface = FakeSurface()

    provider = MockActionProvider(
        actions=[
            AgentAction(
                action=ActionType.WAIT,
                value="10",
                reason="Wait.",
                risk_hint=(
                    RiskLevel.SAFE
                ),
            ),

            AgentAction(
                action=ActionType.WAIT,
                value="10",
                reason="Wait again.",
                risk_hint=(
                    RiskLevel.SAFE
                ),
            ),
        ]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(),  # type: ignore[arg-type]

        max_steps=2,
    )

    async with surface:

        result = await engine.run(
            goal="Never complete.",

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == DiscoveryStatus.MAX_STEPS
    )

    assert len(
        result.steps
    ) == 2


@pytest.mark.asyncio
async def test_resolution_failure_fails_closed():

    surface = FakeSurface(
        fail_resolution=True
    )

    provider = MockActionProvider(
        actions=[
            AgentAction(
                action=(
                    ActionType.CLICK
                ),

                target=target(
                    "Missing button"
                ),

                reason="Click.",

                risk_hint=(
                    RiskLevel.SAFE
                ),
            )
        ]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(),  # type: ignore[arg-type]
    )

    async with surface:

        result = await engine.run(
            goal="Test.",

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == DiscoveryStatus.FAILED
    )

    assert (
        "Target resolution failed"
        in result.message
    )


@pytest.mark.asyncio
async def test_failed_success_condition_stops():

    surface = FakeSurface(
        condition_result=False
    )

    provider = MockActionProvider(
        actions=[
            AgentAction(
                action=ActionType.FILL,

                target=target(
                    "Member ID input"
                ),

                value="1001",

                reason="Enter ID.",

                success_condition=(
                    Condition(
                        type=(
                            ConditionType
                            .TEXT_PRESENT
                        ),

                        value=(
                            "Member Details"
                        ),

                        timeout_ms=100,
                    )
                ),

                risk_hint=(
                    RiskLevel.SAFE
                ),
            )
        ]
    )

    engine = DiscoveryEngine(
        surface=surface,
        provider=provider,

        policy=FakePolicy(),  # type: ignore[arg-type]
    )

    async with surface:

        result = await engine.run(
            goal="Test condition.",

            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
        )

    assert (
        result.status
        == DiscoveryStatus.FAILED
    )

    assert (
        result.steps[0]
        .success_condition_passed
        is False
    )