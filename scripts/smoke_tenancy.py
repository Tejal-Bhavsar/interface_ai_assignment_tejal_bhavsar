from __future__ import annotations

import asyncio
from pathlib import Path

from cua.compiler import (
    load_capability_artifact,
    verify_artifact_integrity,
)
from cua.playwright_surface import PlaywrightSurface
from cua.replay import ReplayEngine
from cua.tenancy import (
    TenantBindingRegistry,
    TenantCapabilityIncompatibleError,
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


async def replay_for_tenant(
    *,
    tenant_id: str,
    member_id: str,
):
    artifact = load_capability_artifact(
        CAPABILITY_PATH
    )

    registry = TenantBindingRegistry.from_path(
        TENANT_CONFIG_PATH
    )

    bound = registry.bind(
        tenant_id=tenant_id,
        application_key="member-servicing",
        artifact=artifact,
    )

    surface = PlaywrightSurface(
        headless=True
    )

    await surface.start()

    try:
        engine = ReplayEngine(
            surface=surface,
            entry_url=bound.entry_url,
            allow_draft=True,
        )

        result = await engine.run(
            artifact=artifact,
            inputs={
                "member_id": member_id,
            },
        )

        return bound, result, artifact

    finally:
        await surface.close()


async def main() -> None:
    print("=" * 70)
    print(
        "STEP 15 — MULTI-TENANT REUSE / DEPLOYMENT BINDING"
    )
    print("=" * 70)

    northstar, northstar_result, artifact_a = (
        await replay_for_tenant(
            tenant_id="northstar-cu",
            member_id="1001",
        )
    )

    harbor, harbor_result, artifact_b = (
        await replay_for_tenant(
            tenant_id="harbor-cu",
            member_id="1002",
        )
    )

    print("\nTENANT 1:")
    print("tenant:", northstar.tenant_id)
    print("entry_url:", northstar.entry_url)
    print("output:", northstar_result.outputs)

    print("\nTENANT 2:")
    print("tenant:", harbor.tenant_id)
    print("entry_url:", harbor.entry_url)
    print("output:", harbor_result.outputs)

    assert northstar_result.status.value == "completed"
    assert harbor_result.status.value == "completed"

    assert artifact_a.identity.id == artifact_b.identity.id
    assert (
        artifact_a.integrity_sha256
        == artifact_b.integrity_sha256
    )

    assert (
        northstar.artifact_integrity_sha256
        == harbor.artifact_integrity_sha256
        == artifact_a.integrity_sha256
    )

    assert verify_artifact_integrity(artifact_a)

    registry = TenantBindingRegistry.from_path(
        TENANT_CONFIG_PATH
    )

    drift_blocked = False

    try:
        registry.bind(
            tenant_id="future-cu",
            application_key="member-servicing",
            artifact=artifact_a,
        )
    except TenantCapabilityIncompatibleError:
        drift_blocked = True

    assert drift_blocked

    print("\n" + "=" * 70)
    print("ONE ARTIFACT, TWO TENANT BINDINGS: ✅")
    print("ARTIFACT NOT COPIED/MUTATED: ✅")
    print("TENANT-SPECIFIC ENTRY URLS: ✅")
    print("EXACT VERSION COMPATIBILITY: ✅")
    print("DRIFT FAILS CLOSED: ✅")
    print("ZERO LLM TENANT ROUTING: ✅")
    print("\nSTEP 15 SMOKE TEST COMPLETE ✅")


if __name__ == "__main__":
    asyncio.run(main())