import pytest

from cua.models import (
    FailureCategory,
    RecoveryStrategy,
)

from cua.profiles import get_profile


def test_load_legacycore_profile():
    profile = get_profile(
        "legacycore-x"
    )

    assert (
        profile.vendor_family
        == "legacycore-x"
    )

    assert (
        profile.profile_version
        == "1.0"
    )


def test_member_not_found_is_business_outcome():
    profile = get_profile(
        "legacycore-x"
    )

    codes = {
        rule.code
        for rule in profile.business_outcomes
    }

    assert "MEMBER_NOT_FOUND" in codes


def test_transient_busy_is_recoverable():
    profile = get_profile(
        "legacycore-x"
    )

    rule = next(
        rule
        for rule in profile.recoveries
        if rule.code == "TRANSIENT_BUSY"
    )

    assert (
        rule.strategy
        == RecoveryStrategy.RELOAD
    )

    assert rule.max_attempts == 1


def test_permission_denied_is_hard_failure():
    profile = get_profile(
        "legacycore-x"
    )

    rule = next(
        rule
        for rule in profile.failures
        if rule.code == "PERMISSION_DENIED"
    )

    assert (
        rule.category
        == FailureCategory.HARD_FAILURE
    )

    assert (
        rule.escalate_to_human
        is False
    )


def test_security_verification_escalates():
    profile = get_profile(
        "legacycore-x"
    )

    rule = next(
        rule
        for rule in profile.failures
        if (
            rule.code
            == "SECURITY_VERIFICATION"
        )
    )

    assert rule.escalate_to_human is True


def test_unknown_vendor_is_rejected():
    with pytest.raises(KeyError):
        get_profile(
            "does-not-exist"
        )