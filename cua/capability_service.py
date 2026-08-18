from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cua.capability_catalog import (
    CapabilityCatalog,
)
from cua.evidence import (
    EvidenceRecorder,
)
from cua.playwright_surface import (
    PlaywrightSurface,
)
from cua.policy import PolicyEngine
from cua.replay import (
    ReplayApprovalError,
    ReplayEngine,
    ReplayResult,
)
from cua.surface import (
    ComputerSurface,
)
from cua.tenancy import (
    BoundCapability,
    TenantBindingRegistry,
)


SurfaceFactory = Callable[
    [],
    ComputerSurface,
]


class CapabilityInvocationRequest(
    BaseModel
):
    """
    Agent-facing invocation contract.

    Version is explicit. We deliberately avoid an implicit
    "latest" because silently switching automation versions is
    undesirable for regulated workflows.
    """

    version: str = Field(
        min_length=1
    )

    tenant_id: str = Field(
        min_length=1
    )

    application_key: str = Field(
        min_length=1
    )

    arguments: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )


class CapabilityInvocationResponse(
    BaseModel
):
    capability_id: str
    capability_version: str

    tenant_id: str
    binding_id: str

    status: str

    outputs: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )

    checkpoint_passed: bool

    runtime_state_code: (
        str | None
    ) = None

    failed_step_id: (
        str | None
    ) = None

    message: str

    recovery_count: int = 0
    human_intervention_count: int = 0

    evidence_run_id: (
        str | None
    ) = None


class CapabilityService:
    """
    The seam an upstream AI agent calls.

    Responsibilities:
      1. resolve a saved capability by exact id/version,
      2. bind it to a tenant deployment,
      3. create a fresh surface,
      4. invoke deterministic ReplayEngine,
      5. return the structured result.

    It does NOT ask an LLM how to execute the UI.
    """

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog,
        tenant_registry: (
            TenantBindingRegistry
        ),
        evidence_root: Path | str,
        policy: PolicyEngine,
        surface_factory: (
            SurfaceFactory
            | None
        ) = None,
        allow_draft: bool = False,
    ):
        self.catalog = catalog

        self.tenant_registry = (
            tenant_registry
        )

        self.evidence_root = Path(
            evidence_root
        )

        self.policy = policy

        self.allow_draft = (
            allow_draft
        )

        self.surface_factory = (
            surface_factory
            or (
                lambda:
                    PlaywrightSurface(
                        headless=True
                    )
            )
        )

    async def invoke(
        self,
        *,
        capability_id: str,
        request: (
            CapabilityInvocationRequest
        ),
    ) -> CapabilityInvocationResponse:
        artifact = self.catalog.get(
            capability_id=(
                capability_id
            ),
            version=request.version,
        )

        if (
            artifact
            .identity
            .approval_state
            .value
            == "draft"
            and not self.allow_draft
        ):
            raise ReplayApprovalError(
                (
                    "Draft capabilities "
                    "cannot be invoked by "
                    "the agent-facing API."
                )
            )

        bound: BoundCapability = (
            self
            .tenant_registry
            .bind(
                tenant_id=(
                    request.tenant_id
                ),
                application_key=(
                    request
                    .application_key
                ),
                artifact=artifact,
            )
        )

        evidence = EvidenceRecorder(
            root=self.evidence_root
        )

        surface = (
            self.surface_factory()
        )

        await surface.start()

        try:
            engine = ReplayEngine(
                surface=surface,
                entry_url=(
                    bound.entry_url
                ),
                allow_draft=(
                    self.allow_draft
                ),
                evidence=evidence,
                policy=self.policy,
            )

            result: ReplayResult = (
                await engine.run(
                    artifact=artifact,
                    inputs=(
                        request.arguments
                    ),
                )
            )

        finally:
            await surface.close()

        runtime_code = None

        if (
            result.runtime_state
            is not None
        ):
            runtime_code = (
                result
                .runtime_state
                .code
            )

        return (
            CapabilityInvocationResponse(
                capability_id=(
                    result
                    .capability_id
                ),
                capability_version=(
                    result
                    .capability_version
                ),
                tenant_id=(
                    bound.tenant_id
                ),
                binding_id=(
                    bound.binding_id
                ),
                status=(
                    result.status.value
                ),
                outputs=(
                    result.outputs
                ),
                checkpoint_passed=(
                    result
                    .checkpoint_passed
                ),
                runtime_state_code=(
                    runtime_code
                ),
                failed_step_id=(
                    result
                    .failed_step_id
                ),
                message=(
                    result.message
                ),
                recovery_count=(
                    result
                    .recovery_count
                ),
                human_intervention_count=(
                    result
                    .human_intervention_count
                ),
                evidence_run_id=(
                    evidence.run_id
                ),
            )
        )