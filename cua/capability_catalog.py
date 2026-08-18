from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cua.compiler import (
    load_capability_artifact,
    verify_artifact_integrity,
)
from cua.models import (
    ApprovalState,
    CapabilityArtifact,
    TypedField,
)


class CapabilityCatalogError(
    RuntimeError
):
    pass


class CapabilityNotFoundError(
    CapabilityCatalogError
):
    pass


class CapabilityVersionNotFoundError(
    CapabilityCatalogError
):
    pass


class CapabilityCatalogEntry(
    BaseModel
):
    """
    Agent-facing, reviewable contract for one saved capability.

    The caller sees WHAT the capability does, WHAT arguments it
    needs, and WHAT it returns. Raw replay steps are deliberately
    not required for normal discovery.
    """

    capability_id: str
    name: str
    version: str
    description: str

    approval_state: ApprovalState

    inputs: dict[
        str,
        TypedField,
    ] = Field(
        default_factory=dict
    )

    outputs: dict[
        str,
        TypedField,
    ] = Field(
        default_factory=dict
    )

    checkpoint_type: str

    target: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )

    integrity_sha256: str

    callable: bool


class CapabilityCatalog:
    """
    Load versioned capability artifacts from disk and expose a
    deterministic catalog.

    No LLM is used for capability discovery or routing.
    """

    def __init__(
        self,
        *,
        capability_dir: Path | str,
        allow_draft: bool = False,
    ):
        self.capability_dir = Path(
            capability_dir
        )

        self.allow_draft = (
            allow_draft
        )

        self._artifacts: dict[
            tuple[
                str,
                str,
            ],
            CapabilityArtifact,
        ] = {}

        self.reload()

    def reload(
        self,
    ) -> None:
        if not self.capability_dir.exists():
            raise CapabilityCatalogError(
                (
                    "Capability directory "
                    f"does not exist: "
                    f"{self.capability_dir}"
                )
            )

        loaded: dict[
            tuple[
                str,
                str,
            ],
            CapabilityArtifact,
        ] = {}

        for path in sorted(
            self.capability_dir.glob(
                "*.json"
            )
        ):
            artifact = (
                load_capability_artifact(
                    path
                )
            )

            if not (
                verify_artifact_integrity(
                    artifact
                )
            ):
                raise CapabilityCatalogError(
                    (
                        "Capability artifact "
                        "failed integrity "
                        "verification: "
                        f"{path.name}"
                    )
                )

            key = (
                artifact.identity.id,
                artifact.identity.version,
            )

            if key in loaded:
                existing = loaded[key]

                # It is common during local development to have
                # duplicate filenames or backup copies that point
                # to the exact same immutable artifact.
                #
                # If identity + version + integrity are identical,
                # safely deduplicate them in the catalog.
                if (
                    existing.integrity_sha256
                    == artifact.integrity_sha256
                ):
                    continue

                # Same id/version but different content is a real
                # catalog conflict and must fail closed.
                raise CapabilityCatalogError(
                    (
                        "Conflicting capability "
                        "artifacts share the same "
                        "id/version but have "
                        "different integrity hashes: "
                        f"{key!r}"
                    )
                )

            loaded[key] = artifact

        self._artifacts = loaded

    def _is_callable(
        self,
        artifact: CapabilityArtifact,
    ) -> bool:
        if (
            artifact
            .identity
            .approval_state
            == ApprovalState.DRAFT
        ):
            return self.allow_draft

        return True

    @staticmethod
    def _entry(
        artifact: CapabilityArtifact,
        *,
        callable_now: bool,
    ) -> CapabilityCatalogEntry:
        return CapabilityCatalogEntry(
            capability_id=(
                artifact.identity.id
            ),
            name=(
                artifact.identity.name
            ),
            version=(
                artifact.identity.version
            ),
            description=(
                artifact
                .identity
                .description
            ),
            approval_state=(
                artifact
                .identity
                .approval_state
            ),
            inputs=artifact.inputs,
            outputs=artifact.outputs,
            checkpoint_type=(
                artifact
                .checkpoint
                .type
                .value
            ),
            target=(
                artifact
                .target
                .model_dump(
                    mode="json"
                )
            ),
            integrity_sha256=(
                artifact
                .integrity_sha256
            ),
            callable=(
                callable_now
            ),
        )

    def list(
        self,
    ) -> list[
        CapabilityCatalogEntry
    ]:
        entries: list[
            CapabilityCatalogEntry
        ] = []

        for key in sorted(
            self._artifacts
        ):
            artifact = (
                self._artifacts[
                    key
                ]
            )

            entries.append(
                self._entry(
                    artifact,
                    callable_now=(
                        self._is_callable(
                            artifact
                        )
                    ),
                )
            )

        return entries

    def get(
        self,
        *,
        capability_id: str,
        version: str,
    ) -> CapabilityArtifact:
        key = (
            capability_id,
            version,
        )

        artifact = (
            self._artifacts.get(
                key
            )
        )

        if artifact is not None:
            return artifact

        capability_exists = any(
            item_id
            == capability_id
            for (
                item_id,
                _,
            )
            in self._artifacts
        )

        if capability_exists:
            raise (
                CapabilityVersionNotFoundError(
                    (
                        "Unknown version "
                        f"'{version}' for "
                        "capability "
                        f"'{capability_id}'."
                    )
                )
            )

        raise CapabilityNotFoundError(
            (
                "Unknown capability: "
                f"'{capability_id}'."
            )
        )

    def describe(
        self,
        *,
        capability_id: str,
        version: str,
    ) -> CapabilityCatalogEntry:
        artifact = self.get(
            capability_id=(
                capability_id
            ),
            version=version,
        )

        return self._entry(
            artifact,
            callable_now=(
                self._is_callable(
                    artifact
                )
            ),
        )