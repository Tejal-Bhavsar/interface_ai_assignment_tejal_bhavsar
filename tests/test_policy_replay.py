from __future__ import annotations

from cua.models import (
    ActionType,
    PolicyDecision,
    ResolvedTargetInfo,
    RiskLevel,
)
from cua.policy import (
    PolicyConfig,
    PolicyEngine,
)


def _policy() -> PolicyEngine:
    return PolicyEngine(
        PolicyConfig(
            allowed_origins=[
                "http://127.0.0.1:8000",
            ],
            allowed_route_prefixes=[
                "/legacy",
            ],
            allowed_actions=[
                ActionType.NAVIGATE,
                ActionType.CLICK,
                ActionType.FILL,
                ActionType.SELECT,
                ActionType.EXTRACT,
                ActionType.WAIT,
                ActionType.ASSERT,
            ],
            risky_phrases=[
                "open sub-account",
            ],
            blocked_phrases=[
                "confirm open sub-account",
            ],
            risky_action_mode=(
                "require_human"
            ),
        )
    )


def _live_info(
    text: str,
    *,
    href: str | None = None,
) -> ResolvedTargetInfo:
    return (
        ResolvedTargetInfo
        .model_validate(
            {
                "tag": "button",
                "role": "button",
                "text": text,
                "name": text,
                "aria_label": None,
                "placeholder": None,
                "href": href,
            }
        )
    )


def test_policy_allows_configured_navigation():
    result = (
        _policy()
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


def test_policy_blocks_external_origin():
    result = (
        _policy()
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


def test_policy_blocks_route_prefix_lookalike():
    result = (
        _policy()
        .evaluate_navigation(
            (
                "http://127.0.0.1:8000"
                "/legacyevil"
            )
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )


def test_policy_uses_live_target_for_risky_detection():
    result = (
        _policy()
        .evaluate_action(
            action=ActionType.CLICK,
            current_url=(
                "http://127.0.0.1:8000"
                "/legacy/member/1001/"
                "account/savings"
            ),
            risk_level=RiskLevel.SAFE,
            target_description=(
                "Primary action button"
            ),
            resolved_info=(
                _live_info(
                    "Open Sub-Account"
                )
            ),
        )
    )

    assert (
        result.decision
        == PolicyDecision
        .REQUIRE_HUMAN
    )

    assert (
        result.matched_phrase
        == "open sub-account"
    )

    assert (
        result.evaluated_live_target
        is True
    )


def test_blocked_phrase_wins_over_risky_phrase():
    result = (
        _policy()
        .evaluate_action(
            action=ActionType.CLICK,
            current_url=(
                "http://127.0.0.1:8000"
                "/legacy/member/1001/"
                "open-subaccount"
            ),
            risk_level=RiskLevel.SAFE,
            target_description=(
                "Primary action button"
            ),
            resolved_info=(
                _live_info(
                    (
                        "Confirm Open "
                        "Sub-Account"
                    )
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


def test_irreversible_risk_is_always_blocked():
    result = (
        _policy()
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
                "Generic button"
            ),
            resolved_info=(
                _live_info(
                    "Generic button"
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
        == (
            "POLICY_IRREVERSIBLE_BLOCKED"
        )
    )


def test_post_action_url_is_checked():
    result = (
        _policy()
        .evaluate_current_url(
            (
                "http://127.0.0.1:8000"
                "/outside"
            )
        )
    )

    assert (
        result.decision
        == PolicyDecision.BLOCK
    )

    assert (
        result.code
        == (
            "POLICY_POST_ACTION_URL_BLOCKED"
        )
    )