from __future__ import annotations

from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from cua.models import CapabilityArtifact


class TenantBindingError(RuntimeError):
    pass


class TenantNotFoundError(TenantBindingError):
    pass


class TenantApplicationNotFoundError(TenantBindingError):
    pass


class TenantBindingDisabledError(TenantBindingError):
    pass


class TenantCapabilityIncompatibleError(TenantBindingError):
    pass


class DriftPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"


class CapabilityCompatibility(BaseModel):
    capability_id: str = Field(min_length=1)
    allowed_versions: list[str] = Field(min_length=1)
    integrity_sha256: str | None = None


class TenantApplicationBinding(BaseModel):
    """
    Concrete deployment configuration for one tenant/application.

    The reusable capability artifact stays tenant-agnostic.
    """

    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    application_key: str = Field(min_length=1)
    vendor_product: str = Field(min_length=1)
    compatibility_key: str = Field(min_length=1)
    entry_url: str = Field(min_length=1)
    enabled: bool = True
    drift_policy: DriftPolicy = DriftPolicy.FAIL_CLOSED
    capabilities: list[CapabilityCompatibility] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("entry_url")
    @classmethod
    def validate_entry_url(cls, value: str) -> str:
        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "Tenant entry_url must use http or https."
            )

        if not parsed.netloc:
            raise ValueError(
                "Tenant entry_url must include a host."
            )

        if parsed.username or parsed.password:
            raise ValueError(
                "Tenant entry_url must not embed credentials."
            )

        return value.rstrip("/")


class TenantRegistryDocument(BaseModel):
    schema_version: str = "1.0"
    bindings: list[TenantApplicationBinding] = Field(default_factory=list)


class BoundCapability(BaseModel):
    """
    Runtime execution plan: WHERE an immutable capability runs.
    """

    tenant_id: str
    binding_id: str
    application_key: str
    vendor_product: str
    compatibility_key: str
    entry_url: str

    capability_id: str
    capability_version: str
    artifact_integrity_sha256: str

    drift_policy: DriftPolicy
    source_tenant: str | None = None


class TenantBindingRegistry:
    """
    Small deployment registry for record-once/replay-many reuse.

    CapabilityArtifact = HOW the automation runs.
    TenantApplicationBinding = WHERE it runs.
    """

    def __init__(self, document: TenantRegistryDocument):
        self.document = document
        self._bindings: dict[
            tuple[str, str],
            TenantApplicationBinding,
        ] = {}

        for binding in document.bindings:
            key = (
                binding.tenant_id,
                binding.application_key,
            )

            if key in self._bindings:
                raise TenantBindingError(
                    f"Duplicate tenant application binding: {key!r}"
                )

            self._bindings[key] = binding

    @classmethod
    def from_path(
        cls,
        path: Path | str,
    ) -> "TenantBindingRegistry":
        source = Path(path)

        document = TenantRegistryDocument.model_validate_json(
            source.read_text(encoding="utf-8")
        )

        return cls(document)

    def get_binding(
        self,
        *,
        tenant_id: str,
        application_key: str,
    ) -> TenantApplicationBinding:
        key = (
            tenant_id,
            application_key,
        )

        binding = self._bindings.get(key)

        if binding is None:
            tenant_exists = any(
                item.tenant_id == tenant_id
                for item in self.document.bindings
            )

            if tenant_exists:
                raise TenantApplicationNotFoundError(
                    (
                        f"Tenant '{tenant_id}' has no binding for "
                        f"application '{application_key}'."
                    )
                )

            raise TenantNotFoundError(
                f"Unknown tenant: '{tenant_id}'."
            )

        if not binding.enabled:
            raise TenantBindingDisabledError(
                (
                    "Tenant application binding "
                    f"'{binding.binding_id}' is disabled."
                )
            )

        return binding

    @staticmethod
    def _find_compatibility(
        *,
        binding: TenantApplicationBinding,
        artifact: CapabilityArtifact,
    ) -> CapabilityCompatibility:
        capability_id = artifact.identity.id

        for compatibility in binding.capabilities:
            if compatibility.capability_id == capability_id:
                return compatibility

        raise TenantCapabilityIncompatibleError(
            (
                f"Capability '{capability_id}' is not approved "
                f"for tenant binding '{binding.binding_id}'."
            )
        )

    def bind(
        self,
        *,
        tenant_id: str,
        application_key: str,
        artifact: CapabilityArtifact,
    ) -> BoundCapability:
        """
        Bind safely and fail closed on unknown compatibility.
        """

        binding = self.get_binding(
            tenant_id=tenant_id,
            application_key=application_key,
        )

        compatibility = self._find_compatibility(
            binding=binding,
            artifact=artifact,
        )

        version = artifact.identity.version

        if version not in compatibility.allowed_versions:
            raise TenantCapabilityIncompatibleError(
                (
                    f"Capability version '{version}' is not approved "
                    f"for tenant binding '{binding.binding_id}'. "
                    "Replay is blocked until compatibility is re-verified."
                )
            )

        if (
            compatibility.integrity_sha256 is not None
            and compatibility.integrity_sha256
            != artifact.integrity_sha256
        ):
            raise TenantCapabilityIncompatibleError(
                (
                    "Capability integrity does not match the "
                    "tenant's verified artifact pin."
                )
            )

        return BoundCapability(
            tenant_id=binding.tenant_id,
            binding_id=binding.binding_id,
            application_key=binding.application_key,
            vendor_product=binding.vendor_product,
            compatibility_key=binding.compatibility_key,
            entry_url=binding.entry_url,
            capability_id=artifact.identity.id,
            capability_version=artifact.identity.version,
            artifact_integrity_sha256=artifact.integrity_sha256,
            drift_policy=binding.drift_policy,
            source_tenant=artifact.discovery.source_tenant,
        )