from __future__ import annotations

import os

from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)

from cua.capability_catalog import (
    CapabilityCatalog,
    CapabilityCatalogEntry,
    CapabilityNotFoundError,
    CapabilityVersionNotFoundError,
)
from cua.capability_service import (
    CapabilityInvocationRequest,
    CapabilityInvocationResponse,
    CapabilityService,
)
from cua.policy import PolicyEngine
from cua.replay import (
    ReplayApprovalError,
    ReplayInputError,
)
from cua.tenancy import (
    TenantApplicationNotFoundError,
    TenantBindingDisabledError,
    TenantBindingRegistry,
    TenantCapabilityIncompatibleError,
    TenantNotFoundError,
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

TENANT_BINDINGS_PATH = (
    PROJECT_ROOT
    / "config"
    / "tenant_bindings.json"
)

POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "policy.json"
)

AGENT_API_EVIDENCE_ROOT = (
    PROJECT_ROOT
    / "evidence"
    / "agent_api"
)


def _env_bool(
    name: str,
    *,
    default: bool = False,
) -> bool:
    raw = os.getenv(
        name
    )

    if raw is None:
        return default

    return (
        raw.strip().lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def create_app(
    *,
    allow_draft: (
        bool | None
    ) = None,
) -> FastAPI:
    """
    Create the agent-facing automation API.

    Production default:
        draft capability invocation is disabled.

    Take-home smoke:
        explicitly set CUA_ALLOW_DRAFT_CAPABILITIES=1 because
        the saved demonstration artifact is still draft.
    """

    if allow_draft is None:
        allow_draft = _env_bool(
            "CUA_ALLOW_DRAFT_CAPABILITIES",
            default=False,
        )

    catalog = CapabilityCatalog(
        capability_dir=(
            CAPABILITY_DIR
        ),
        allow_draft=(
            allow_draft
        ),
    )

    tenant_registry = (
        TenantBindingRegistry
        .from_path(
            TENANT_BINDINGS_PATH
        )
    )

    policy = PolicyEngine.from_path(
        POLICY_PATH
    )

    service = CapabilityService(
        catalog=catalog,
        tenant_registry=(
            tenant_registry
        ),
        evidence_root=(
            AGENT_API_EVIDENCE_ROOT
        ),
        policy=policy,
        allow_draft=(
            allow_draft
        ),
    )

    app = FastAPI(
        title=(
            "CUA Agent Capability API"
        ),
        version="1.0.0",
        description=(
            "Agent-facing catalog and "
            "deterministic capability "
            "invocation API."
        ),
    )

    # Keep references available for tests/introspection.
    app.state.capability_catalog = (
        catalog
    )

    app.state.capability_service = (
        service
    )

    @app.get(
        "/health"
    )
    async def health():
        return {
            "status": "ok",
            "capabilities": len(
                catalog.list()
            ),
            "draft_invocation_enabled":
                allow_draft,
            "runtime_policy_enabled":
                True,
        }

    @app.get(
        "/v1/capabilities",
        response_model=list[
            CapabilityCatalogEntry
        ],
    )
    async def list_capabilities():
        return catalog.list()

    @app.get(
        "/v1/capabilities/{capability_id}",
        response_model=(
            CapabilityCatalogEntry
        ),
    )
    async def describe_capability(
        capability_id: str,
        version: str = Query(
            ...,
            min_length=1,
        ),
    ):
        try:
            return catalog.describe(
                capability_id=(
                    capability_id
                ),
                version=version,
            )

        except (
            CapabilityNotFoundError
        ) as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        except (
            CapabilityVersionNotFoundError
        ) as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

    @app.post(
        (
            "/v1/capabilities/"
            "{capability_id}/invoke"
        ),
        response_model=(
            CapabilityInvocationResponse
        ),
    )
    async def invoke_capability(
        capability_id: str,
        request: (
            CapabilityInvocationRequest
        ),
    ):
        try:
            return await service.invoke(
                capability_id=(
                    capability_id
                ),
                request=request,
            )

        except (
            CapabilityNotFoundError,
            CapabilityVersionNotFoundError,
            TenantNotFoundError,
            TenantApplicationNotFoundError,
        ) as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        except (
            TenantBindingDisabledError,
            TenantCapabilityIncompatibleError,
            ReplayApprovalError,
        ) as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        except ReplayInputError as exc:
            # The replay input validator reports field names and
            # type mismatches, not raw sensitive values.
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    return app


app = create_app()