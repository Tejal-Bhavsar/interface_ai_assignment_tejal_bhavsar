from __future__ import annotations

from pathlib import Path

import pytest

from cua.compiler import load_capability_artifact
from cua.tenancy import (
    TenantBindingRegistry,
    TenantCapabilityIncompatibleError,
    TenantNotFoundError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CAPABILITY_PATH = (
    PROJECT_ROOT
    / "capabilities"
    / "lookup_savings_balance.v1.json"
)

TENANT_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "tenant_bindings.json"
)


def _artifact():
    return load_capability_artifact(CAPABILITY_PATH)


def _registry():
    return TenantBindingRegistry.from_path(
        TENANT_CONFIG_PATH
    )


def test_same_artifact_binds_to_two_tenants():
    artifact = _artifact()
    registry = _registry()

    first = registry.bind(
        tenant_id="northstar-cu",
        application_key="member-servicing",
        artifact=artifact,
    )

    second = registry.bind(
        tenant_id="harbor-cu",
        application_key="member-servicing",
        artifact=artifact,
    )

    assert (
        first.capability_id
        == second.capability_id
        == artifact.identity.id
    )

    assert (
        first.artifact_integrity_sha256
        == second.artifact_integrity_sha256
        == artifact.integrity_sha256
    )

    assert first.entry_url != second.entry_url

    assert (
        first.compatibility_key
        == second.compatibility_key
        == "legacycore-x:v1"
    )


def test_unknown_tenant_fails_closed():
    with pytest.raises(TenantNotFoundError):
        _registry().bind(
            tenant_id="missing-cu",
            application_key="member-servicing",
            artifact=_artifact(),
        )


def test_incompatible_version_fails_closed():
    with pytest.raises(
        TenantCapabilityIncompatibleError
    ):
        _registry().bind(
            tenant_id="future-cu",
            application_key="member-servicing",
            artifact=_artifact(),
        )


def test_binding_does_not_mutate_artifact():
    artifact = _artifact()
    before = artifact.model_dump(mode="json")

    _registry().bind(
        tenant_id="northstar-cu",
        application_key="member-servicing",
        artifact=artifact,
    )

    after = artifact.model_dump(mode="json")

    assert before == after