from __future__ import annotations

from pathlib import Path

import pytest

from cua.capability_catalog import (
    CapabilityCatalog,
    CapabilityNotFoundError,
    CapabilityVersionNotFoundError,
)
from cua.capability_service import (
    CapabilityInvocationRequest,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

CAPABILITY_DIR = (
    PROJECT_ROOT
    / "capabilities"
)


def _catalog(
    *,
    allow_draft: bool = True,
):
    return CapabilityCatalog(
        capability_dir=(
            CAPABILITY_DIR
        ),
        allow_draft=(
            allow_draft
        ),
    )


def test_catalog_exposes_typed_contract():
    entries = _catalog().list()

    entry = next(
        item
        for item in entries
        if item.capability_id
        == "lookup_savings_balance"
    )

    assert (
        entry.version
        == "1.0.0"
    )

    assert (
        "member_id"
        in entry.inputs
    )

    assert (
        "current_savings_balance"
        in entry.outputs
    )

    assert (
        entry.integrity_sha256
    )

    assert (
        entry.callable
        is True
    )


def test_draft_catalog_entry_not_callable_by_default():
    entries = _catalog(
        allow_draft=False
    ).list()

    entry = next(
        item
        for item in entries
        if item.capability_id
        == "lookup_savings_balance"
    )

    assert (
        entry.callable
        is False
    )


def test_exact_version_lookup():
    artifact = _catalog().get(
        capability_id=(
            "lookup_savings_balance"
        ),
        version="1.0.0",
    )

    assert (
        artifact.identity.id
        == "lookup_savings_balance"
    )


def test_unknown_capability_is_explicit():
    with pytest.raises(
        CapabilityNotFoundError
    ):
        _catalog().get(
            capability_id="missing",
            version="1.0.0",
        )


def test_unknown_version_is_explicit():
    with pytest.raises(
        CapabilityVersionNotFoundError
    ):
        _catalog().get(
            capability_id=(
                "lookup_savings_balance"
            ),
            version="99.0.0",
        )


def test_invocation_contract_is_typed():
    request = (
        CapabilityInvocationRequest(
            version="1.0.0",
            tenant_id="northstar-cu",
            application_key=(
                "member-servicing"
            ),
            arguments={
                "member_id":
                    "1002",
            },
        )
    )

    assert (
        request.version
        == "1.0.0"
    )

    assert (
        request.arguments[
            "member_id"
        ]
        == "1002"
    )