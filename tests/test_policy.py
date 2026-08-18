from __future__ import annotations

from pathlib import Path

from cua.models import (
    ActionType,
    PolicyDecision,
    ResolvedTargetInfo,
    RiskLevel,
)

from cua.policy import (
    PolicyEngine,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "policy.json"
)


def engine() -> PolicyEngine:
    return PolicyEngine.from_path(
        POLICY_PATH
    )


def test_allowed_legacy_url():
    result = (
        engine()
        .evaluate_navigation(
            (
                "http://127.0.0.1:8000"
                "/legacy/member/1001"
            )
        )
    )

    assert (
        result.decision
        == PolicyDecision.ALLOW
    )

    assert (
        result.code
        == "POLICY_ALLOW"
    )


def test_external_origin_is_blocked():
    result = (
        engine()
        .evaluate_navigation(
            "https://example.com/legacy"
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == "POLICY_URL_BLOCKED"
    )


def test_non_allowlisted_route_is_blocked():
    result = (
        engine()
        .evaluate_navigation(
            (
                "http://127.0.0.1:8000"
                "/admin"
            )
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == "POLICY_URL_BLOCKED"
    )


def test_prefix_cannot_match_legacy_evil():
    result = (
        engine()
        .evaluate_navigation(
            (
                "http://127.0.0.1:8000"
                "/legacy-evil"
            )
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == "POLICY_URL_BLOCKED"
    )


def test_safe_search_click_is_allowed():
    live = ResolvedTargetInfo(
        tag="button",
        role="button",
        text="Search",
        name="Search",
    )

    result = (
        engine()
        .evaluate_action(
            action=ActionType.CLICK,

            current_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),

            risk_level=(
                RiskLevel.SAFE
            ),

            target_description=(
                "Member search button"
            ),

            resolved_info=live,
        )
    )

    assert (
        result.decision
        == PolicyDecision.ALLOW
    )

    assert (
        result.code
        == "POLICY_ALLOW"
    )

    assert (
        result.evaluated_live_target
        is True
    )


def test_risky_open_subaccount_requires_human():
    """
    "Open Sub-Account" is risky.

    The stronger phrase "Confirm Open Sub-Account" is intentionally
    globally BLOCKED and is tested separately.
    """

    live = ResolvedTargetInfo(
        tag="button",
        role="button",
        text="Open Sub-Account",
        name="Open Sub-Account",
    )

    result = (
        engine()
        .evaluate_action(
            action=ActionType.CLICK,

            current_url=(
                "http://127.0.0.1:8000"
                "/legacy/member/1001"
                "/account/savings"
            ),

            risk_level=(
                RiskLevel.SAFE
            ),

            target_description=(
                "Primary action"
            ),

            resolved_info=live,
        )
    )

    assert (
        result.decision
        == PolicyDecision.REQUIRE_HUMAN
    )

    assert (
        result.code
        == "POLICY_HUMAN_REQUIRED"
    )

    assert (
        result.matched_phrase
        == "open sub-account"
    )

    assert (
        result.evaluated_live_target
        is True
    )


def test_irreversible_target_is_blocked():
    result = (
        engine()
        .evaluate_action(
            action=ActionType.CLICK,

            current_url=(
                "http://127.0.0.1:8000"
                "/legacy/member/1001"
            ),

            risk_level=(
                RiskLevel.IRREVERSIBLE
            ),

            target_description=(
                "Destructive operation"
            ),

            resolved_info=(
                ResolvedTargetInfo(
                    tag="button",
                    role="button",
                    text="Proceed",
                    name="Proceed",
                )
            ),
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == "POLICY_IRREVERSIBLE_BLOCKED"
    )


def test_live_target_can_override_innocent_description():
    """
    The artifact/agent description looks harmless, but the real
    resolved button is a globally blocked operation.
    """

    result = (
        engine()
        .evaluate_action(
            action=ActionType.CLICK,

            current_url=(
                "http://127.0.0.1:8000"
                "/legacy/member/1001"
                "/open-subaccount"
            ),

            risk_level=(
                RiskLevel.SAFE
            ),

            target_description="Continue",

            resolved_info=(
                ResolvedTargetInfo(
                    tag="button",
                    role="button",
                    text=(
                        "Confirm Open "
                        "Sub-Account"
                    ),
                    name=(
                        "Confirm Open "
                        "Sub-Account"
                    ),
                )
            ),
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == "POLICY_BLOCKED_PHRASE"
    )

    assert (
        result.matched_phrase
        == "confirm open sub-account"
    )

    assert (
        result.evaluated_live_target
        is True
    )


def test_external_link_is_blocked_before_click():
    live = ResolvedTargetInfo(
        tag="a",
        role="link",
        text="Continue",
        name="Continue",
        href="https://example.com",
    )

    result = (
        engine()
        .evaluate_action(
            action=ActionType.CLICK,

            current_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),

            risk_level=(
                RiskLevel.SAFE
            ),

            target_description="Continue",

            resolved_info=live,

            destination_url=(
                live.href
            ),
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == "POLICY_DESTINATION_BLOCKED"
    )

    assert (
        result.destination_url_allowed
        is False
    )