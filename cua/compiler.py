from __future__ import annotations

import hashlib
import json
import re

from collections.abc import (
    Mapping,
    Sequence,
)
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    Field,
)

from cua.models import (
    ActionType,
    AgentAction,
    ApplicationProfile,
    ApprovalState,
    CapabilityArtifact,
    CapabilityIdentity,
    CapabilityStep,
    Condition,
    ConditionType,
    DiscoveryMetadata,
    DiscoveryRunResult,
    DiscoveryStatus,
    LocatorKind,
    SafetyContract,
    TargetDescriptor,
    TargetSpec,
    TypedField,
    ValueType,
)


# ============================================================
# Errors
# ============================================================


class CapabilityCompilationError(
    RuntimeError
):
    """
    Raised when a discovery run cannot safely be compiled
    into a reusable capability.
    """

    pass


# ============================================================
# Compile request models
# ============================================================


class CompileInput(
    BaseModel
):
    """
    Declares one reusable capability input.

    example_value is the concrete value used during the
    discovery run.

    It is used only during compilation and must not remain
    in the resulting capability artifact.
    """

    field: TypedField

    example_value: Any


class CapabilityCompileSpec(
    BaseModel
):
    """
    Explicit metadata required to turn one successful
    discovery run into a reusable capability.
    """

    capability_id: str = Field(
        min_length=1
    )

    name: str = Field(
        min_length=1
    )

    version: str = Field(
        min_length=1
    )

    description: str = Field(
        min_length=1
    )

    target: TargetSpec

    inputs: dict[
        str,
        CompileInput,
    ] = Field(
        default_factory=dict
    )

    # If omitted, output types are inferred from the
    # successful discovery result.
    #
    # Inferred outputs are conservatively marked sensitive.
    outputs: (
        dict[
            str,
            TypedField,
        ]
        | None
    ) = None

    checkpoint: (
        Condition
        | None
    ) = None

    safety: SafetyContract

    approval_state: (
        ApprovalState
    ) = ApprovalState.DRAFT

    source_tenant: (
        str | None
    ) = None


# ============================================================
# Placeholder helpers
# ============================================================


def capability_placeholder(
    input_name: str,
) -> str:
    """
    Canonical capability parameter syntax.

    Example:

        member_id
            ↓
        {{member_id}}
    """

    return (
        "{{"
        + input_name
        + "}}"
    )


# ============================================================
# Type validation
# ============================================================


def _matches_value_type(
    value: Any,
    value_type: ValueType,
) -> bool:
    """
    Check whether a concrete discovery value matches the
    declared capability type.
    """

    if value is None:
        return False

    if (
        value_type
        == ValueType.STRING
    ):
        return isinstance(
            value,
            str,
        )

    if (
        value_type
        == ValueType.NUMBER
    ):
        return (
            isinstance(
                value,
                (int, float),
            )
            and not isinstance(
                value,
                bool,
            )
        )

    if (
        value_type
        == ValueType.BOOLEAN
    ):
        return isinstance(
            value,
            bool,
        )

    if (
        value_type
        == ValueType.OBJECT
    ):
        return isinstance(
            value,
            Mapping,
        )

    if (
        value_type
        == ValueType.ARRAY
    ):
        return (
            isinstance(
                value,
                Sequence,
            )
            and not isinstance(
                value,
                (
                    str,
                    bytes,
                    bytearray,
                ),
            )
        )

    return False


def _infer_value_type(
    value: Any,
) -> ValueType:
    """
    Infer our portable ValueType from one runtime value.
    """

    if isinstance(
        value,
        bool,
    ):
        return ValueType.BOOLEAN

    if (
        isinstance(
            value,
            (int, float),
        )
        and not isinstance(
            value,
            bool,
        )
    ):
        return ValueType.NUMBER

    if isinstance(
        value,
        str,
    ):
        return ValueType.STRING

    if isinstance(
        value,
        Mapping,
    ):
        return ValueType.OBJECT

    if (
        isinstance(
            value,
            Sequence,
        )
        and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        return ValueType.ARRAY

    raise CapabilityCompilationError(
        (
            "Cannot infer capability "
            "value type from "
            f"{type(value).__name__}."
        )
    )


# ============================================================
# Deterministic parameterization
# ============================================================


def _example_as_text(
    example: Any,
) -> str | None:
    """
    Convert a scalar discovery example into a textual form
    when it may legitimately appear inside URLs, locators,
    conditions, or descriptions.

    Complex objects and booleans are not converted to text.
    """

    if isinstance(
        example,
        str,
    ):
        return example

    if (
        isinstance(
            example,
            (int, float),
        )
        and not isinstance(
            example,
            bool,
        )
    ):
        return str(
            example
        )

    return None


def _replace_parameter_value(
    text: str,
    *,
    example: str,
    placeholder: str,
) -> tuple[
    str,
    int,
]:
    """
    Replace an explicit discovery input without matching it
    as part of a larger alphanumeric/underscore token.

    Example:

        example = "1001"

        "/member/1001"   -> match
        "Member 1001"    -> match

        "10010"          -> no match
        "ABC1001XYZ"     -> no match
        "acct_1001_prod" -> no match

    This avoids naive substring replacement.
    """

    if not example:
        return text, 0

    escaped = re.escape(
        example
    )

    pattern = re.compile(
        (
            r"(?<![A-Za-z0-9_])"
            + escaped
            + r"(?![A-Za-z0-9_])"
        )
    )

    return pattern.subn(
        placeholder,
        text,
    )


def _parameterize_data(
    value: Any,
    *,
    inputs: dict[
        str,
        CompileInput,
    ],
    usage: dict[
        str,
        int,
    ],
) -> Any:
    """
    Recursively replace explicitly declared discovery
    examples with reusable capability placeholders.

    This function is deterministic.

    It does NOT ask an LLM which fields should become
    parameters.
    """

    # --------------------------------------------------------
    # Strings
    # --------------------------------------------------------

    if isinstance(
        value,
        str,
    ):
        result = value

        # Longest textual values first prevents a shorter
        # input from consuming part of a longer input.
        ordered = sorted(
            inputs.items(),
            key=lambda item: len(
                _example_as_text(
                    item[1]
                    .example_value
                )
                or ""
            ),
            reverse=True,
        )

        for (
            input_name,
            binding,
        ) in ordered:

            example_text = (
                _example_as_text(
                    binding.example_value
                )
            )

            if not example_text:
                continue

            (
                result,
                occurrences,
            ) = _replace_parameter_value(
                result,
                example=example_text,
                placeholder=(
                    capability_placeholder(
                        input_name
                    )
                ),
            )

            usage[
                input_name
            ] += occurrences

        return result

    # --------------------------------------------------------
    # Mapping
    # --------------------------------------------------------

    if isinstance(
        value,
        Mapping,
    ):
        return {
            key: _parameterize_data(
                item,
                inputs=inputs,
                usage=usage,
            )
            for (
                key,
                item,
            ) in value.items()
        }

    # --------------------------------------------------------
    # Sequence
    # --------------------------------------------------------

    if isinstance(
        value,
        list,
    ):
        return [
            _parameterize_data(
                item,
                inputs=inputs,
                usage=usage,
            )
            for item in value
        ]

    if isinstance(
        value,
        tuple,
    ):
        return tuple(
            _parameterize_data(
                item,
                inputs=inputs,
                usage=usage,
            )
            for item in value
        )

    # --------------------------------------------------------
    # Exact non-string primitive
    # --------------------------------------------------------

    for (
        input_name,
        binding,
    ) in inputs.items():

        example = (
            binding.example_value
        )

        if (
            type(value)
            is type(example)
            and value == example
        ):
            usage[
                input_name
            ] += 1

            return (
                capability_placeholder(
                    input_name
                )
            )

    return value


def _parameterize_without_usage_check(
    value: Any,
    *,
    inputs: dict[
        str,
        CompileInput,
    ],
) -> Any:
    """
    Parameterize descriptive/non-executable metadata without
    allowing those replacements to prove that an input
    actually affects capability execution.
    """

    dummy_usage = {
        name: 0
        for name in inputs
    }

    return _parameterize_data(
        value,
        inputs=inputs,
        usage=dummy_usage,
    )


# ============================================================
# Executable-input usage detection
# ============================================================


def _target_locator_payload(
    target: Any,
) -> list[
    dict[str, Any]
]:
    """
    Return only executable locator information.

    Human-readable locator descriptions are intentionally
    excluded so they cannot make an otherwise-unused input
    appear to affect execution.
    """

    if target is None:
        return []

    return [
        locator.model_dump(
            mode="json",
            exclude={
                "description",
            },
        )
        for locator
        in target.locators
    ]


def _condition_execution_payload(
    condition: Condition | None,
) -> Any:
    """
    Return only pieces of a condition that influence runtime
    verification.
    """

    if condition is None:
        return None

    return {
        "value":
            condition.value,

        "output_name":
            condition.output_name,

        "target_locators":
            _target_locator_payload(
                condition.target
            ),
    }


def _action_execution_payload(
    action: AgentAction,
) -> dict[
    str,
    Any,
]:
    """
    Extract only action data that affects actual execution.

    The model's reason and target description are excluded.

    This prevents a declaration such as:

        reason = "Search member 1001"

    from falsely proving that `member_id` is a reusable
    executable input if no actual locator/value depends on it.
    """

    return {
        "value":
            action.value,

        "target_locators":
            _target_locator_payload(
                action.target
            ),

        "success_condition":
            _condition_execution_payload(
                action.success_condition
            ),
    }


def _record_executable_input_usage(
    *,
    action: AgentAction,
    inputs: dict[
        str,
        CompileInput,
    ],
    usage: dict[
        str,
        int,
    ],
) -> None:
    """
    Count parameter usage only in executable action data.
    """

    payload = (
        _action_execution_payload(
            action
        )
    )

    _parameterize_data(
        payload,
        inputs=inputs,
        usage=usage,
    )


# ============================================================
# Step IDs
# ============================================================


def _slugify(
    value: str,
) -> str:
    """
    Create a stable human-readable component for step IDs.
    """

    slug = re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        value.lower(),
    )

    slug = slug.strip(
        "_"
    )

    return slug[:50]


def _step_id(
    *,
    index: int,
    action: AgentAction,
) -> str:
    """
    Generate deterministic ordered step IDs.
    """

    subject = (
        action.output_name
        or (
            action.target.description
            if (
                action.target
                is not None
            )
            else action.action.value
        )
    )

    slug = _slugify(
        subject
    )

    if not slug:
        slug = (
            action.action.value
        )

    return (
        f"step_{index:02d}_"
        f"{action.action.value}_"
        f"{slug}"
    )


# ============================================================
# Artifact integrity
# ============================================================


def compute_artifact_integrity(
    artifact: CapabilityArtifact,
) -> str:
    """
    Compute SHA-256 over canonical artifact JSON while
    excluding the integrity field itself.
    """

    payload = artifact.model_dump(
        mode="json"
    )

    payload.pop(
        "integrity_sha256",
        None,
    )

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest()


def verify_artifact_integrity(
    artifact: CapabilityArtifact,
) -> bool:
    """
    Recompute and verify the capability artifact digest.
    """

    expected = (
        compute_artifact_integrity(
            artifact
        )
    )

    return (
        artifact.integrity_sha256
        == expected
    )


# ============================================================
# Persistent artifact helpers
# ============================================================


def save_capability_artifact(
    artifact: CapabilityArtifact,
    path: Path | str,
) -> Path:
    """
    Save a capability only if its integrity hash is valid.
    """

    if not verify_artifact_integrity(
        artifact
    ):
        raise CapabilityCompilationError(
            (
                "Refusing to save a "
                "capability artifact with "
                "an invalid integrity hash."
            )
        )

    destination = Path(
        path
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_text(
        (
            artifact.model_dump_json(
                indent=2
            )
            + "\n"
        ),
        encoding="utf-8",
    )

    return destination


def load_capability_artifact(
    path: Path | str,
) -> CapabilityArtifact:
    """
    Load and validate artifact structure.

    Integrity verification is intentionally exposed
    separately because Step 11's replay engine will make
    integrity verification an explicit replay gate.
    """

    source = Path(
        path
    )

    return (
        CapabilityArtifact
        .model_validate_json(
            source.read_text(
                encoding="utf-8"
            )
        )
    )


# ============================================================
# Sensitive runtime leak detection
# ============================================================


def _iter_sensitive_scalars(
    value: Any,
):
    """
    Yield sensitive runtime scalar values recursively.

    Strings shorter than four characters are skipped because
    they produce excessive accidental matches against normal
    schema/version metadata.

    Numeric sensitive values are retained because they may
    leak either as numbers or inside model-generated text.
    """

    if value is None:
        return

    if isinstance(
        value,
        str,
    ):
        if len(value) >= 4:
            yield value

        return

    if (
        isinstance(
            value,
            (int, float),
        )
        and not isinstance(
            value,
            bool,
        )
    ):
        yield value
        return

    if isinstance(
        value,
        Mapping,
    ):
        for item in (
            value.values()
        ):
            yield from (
                _iter_sensitive_scalars(
                    item
                )
            )

        return

    if (
        isinstance(
            value,
            Sequence,
        )
        and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        for item in value:
            yield from (
                _iter_sensitive_scalars(
                    item
                )
            )


def _contains_runtime_value(
    value: Any,
    sensitive_value: Any,
) -> bool:
    """
    Search artifact data structurally for a sensitive runtime
    value.

    For strings we use the same token-aware matching semantics
    used for parameterization rather than naive substring
    matching.

    For non-string scalars, exact type/value equality is used.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return any(
            _contains_runtime_value(
                item,
                sensitive_value,
            )
            for item
            in value.values()
        )

    if (
        isinstance(
            value,
            Sequence,
        )
        and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        return any(
            _contains_runtime_value(
                item,
                sensitive_value,
            )
            for item in value
        )

    # --------------------------------------------------------
    # Sensitive value embedded in artifact text
    # --------------------------------------------------------

    if isinstance(
        value,
        str,
    ):
        sensitive_text = (
            _example_as_text(
                sensitive_value
            )
        )

        if sensitive_text:
            (
                _,
                count,
            ) = _replace_parameter_value(
                value,
                example=(
                    sensitive_text
                ),
                placeholder=(
                    "__SENSITIVE_MATCH__"
                ),
            )

            return count > 0

    # --------------------------------------------------------
    # Exact scalar value
    # --------------------------------------------------------

    return (
        type(value)
        is type(
            sensitive_value
        )
        and value
        == sensitive_value
    )


def _assert_no_sensitive_runtime_leaks(
    *,
    artifact: CapabilityArtifact,
    discovery: DiscoveryRunResult,
    spec: CapabilityCompileSpec,
    outputs: dict[
        str,
        TypedField,
    ],
) -> None:
    """
    Fail compilation if a concrete sensitive discovery
    input/output value survives anywhere in the reusable
    artifact.

    This protects against leaks through:

      - action values
      - locators
      - descriptions
      - reasons
      - conditions
      - metadata
      - target information

    We deliberately fail rather than inventing a repaired
    locator or silently deleting information.
    """

    artifact_data = (
        artifact.model_dump(
            mode="json"
        )
    )

    # --------------------------------------------------------
    # Sensitive discovery inputs
    # --------------------------------------------------------

    for (
        input_name,
        binding,
    ) in spec.inputs.items():

        if not (
            binding.field.sensitive
        ):
            continue

        for sensitive_value in (
            _iter_sensitive_scalars(
                binding.example_value
            )
        ):
            if _contains_runtime_value(
                artifact_data,
                sensitive_value,
            ):
                raise (
                    CapabilityCompilationError(
                        (
                            "Sensitive runtime "
                            "input value for "
                            f"'{input_name}' "
                            "remained in the "
                            "compiled artifact."
                        )
                    )
                )

    # --------------------------------------------------------
    # Sensitive discovery outputs
    # --------------------------------------------------------

    for (
        output_name,
        field,
    ) in outputs.items():

        if not field.sensitive:
            continue

        runtime_value = (
            discovery.outputs.get(
                output_name
            )
        )

        for sensitive_value in (
            _iter_sensitive_scalars(
                runtime_value
            )
        ):
            if _contains_runtime_value(
                artifact_data,
                sensitive_value,
            ):
                raise (
                    CapabilityCompilationError(
                        (
                            "Sensitive runtime "
                            "output value for "
                            f"'{output_name}' "
                            "remained in the "
                            "compiled artifact."
                        )
                    )
                )

def _canonicalize_extraction_action(
    *,
    action: AgentAction,
    discovery: DiscoveryRunResult,
) -> AgentAction:

    if (
        action.action
        != ActionType.EXTRACT
    ):
        return action

    if action.target is None:
        return action

    if not action.output_name:
        return action

    if (
        action.output_name
        not in discovery.outputs
    ):
        return action

    runtime_value = (
        discovery.outputs[
            action.output_name
        ]
    )

    runtime_text = (
        _example_as_text(
            runtime_value
        )
    )

    if not runtime_text:
        return action

    target_data = (
        action.target.model_dump(
            mode="json"
        )
    )

    changed = False

    for locator in (
        target_data.get(
            "locators",
            [],
        )
    ):

        locator_value = (
            locator.get(
                "value"
            )
        )

        if (
            locator_value
            != runtime_text
        ):
            continue

        if (
            locator.get("kind")
            == (
                LocatorKind
                .RELATIVE_TEXT
                .value
            )
            and locator.get(
                "reference_text"
            )
            and locator.get(
                "relation"
            )
            == "same_row"
        ):

            locator[
                "value"
            ] = None

            changed = True

    if not changed:
        return action

    canonical_target = (
        TargetDescriptor
        .model_validate(
            target_data
        )
    )

    return action.model_copy(
        update={
            "target":
                canonical_target
        }
    )

def _assert_no_dynamic_output_locator(
    *,
    action: AgentAction,
    discovery: DiscoveryRunResult,
) -> None:

    if (
        action.action
        != ActionType.EXTRACT
    ):
        return

    if action.target is None:
        return

    if not action.output_name:
        return

    if (
        action.output_name
        not in discovery.outputs
    ):
        return

    runtime_value = (
        discovery.outputs[
            action.output_name
        ]
    )

    for locator in (
        action.target.locators
    ):

        locator_data = (
            locator.model_dump(
                mode="json",
                exclude={
                    "description",
                },
            )
        )

        if _contains_runtime_value(
            locator_data,
            runtime_value,
        ):
            raise (
                CapabilityCompilationError(
                    (
                        "Dynamic extraction "
                        f"value for output "
                        f"'{action.output_name}' "
                        "is still being used "
                        "as an executable "
                        "locator. A reusable "
                        "capability must locate "
                        "the output using stable "
                        "UI structure."
                    )
                )
            ) 
# ============================================================
# Compiler
# ============================================================


class CapabilityCompiler:
    """
    Converts one successful discovery result into a typed,
    versioned, reusable capability artifact.

    Discovery observations and concrete extracted values are
    NOT copied into the artifact.

    Compilation itself is deterministic and performs no LLM
    calls.
    """

    def __init__(
        self,
        *,
        application_profile: (
            ApplicationProfile
        ),
    ):
        self.application_profile = (
            application_profile
        )

    # ========================================================
    # Input validation
    # ========================================================

    @staticmethod
    def _validate_inputs(
        spec: CapabilityCompileSpec,
    ) -> None:
        """
        Validate declared capability input examples.
        """

        for (
            name,
            binding,
        ) in spec.inputs.items():

            if not name.strip():
                raise (
                    CapabilityCompilationError(
                        (
                            "Capability input "
                            "names cannot be "
                            "empty."
                        )
                    )
                )

            if (
                binding.example_value
                is None
                and binding.field.required
            ):
                raise (
                    CapabilityCompilationError(
                        (
                            f"Required input "
                            f"'{name}' has no "
                            "discovery example."
                        )
                    )
                )

            if (
                binding.example_value
                is not None
                and not _matches_value_type(
                    binding.example_value,
                    binding.field.type,
                )
            ):
                raise (
                    CapabilityCompilationError(
                        (
                            f"Input '{name}' "
                            f"declares type "
                            f"'{binding.field.type.value}' "
                            "but discovery "
                            f"example has type "
                            f"'{type(binding.example_value).__name__}'."
                        )
                    )
                )

    # ========================================================
    # Output schema
    # ========================================================

    @staticmethod
    def _build_outputs(
        *,
        discovery: DiscoveryRunResult,
        spec: CapabilityCompileSpec,
    ) -> dict[
        str,
        TypedField,
    ]:
        """
        Build or validate the reusable capability output
        contract.

        If outputs are inferred automatically, they are
        marked sensitive by default.

        A reviewer may explicitly declare known-safe outputs
        non-sensitive in CapabilityCompileSpec.
        """

        discovered_names = set(
            discovery.outputs
        )

        # ----------------------------------------------------
        # Infer schema
        # ----------------------------------------------------

        if spec.outputs is None:

            inferred: dict[
                str,
                TypedField,
            ] = {}

            for (
                name,
                value,
            ) in discovery.outputs.items():

                inferred[
                    name
                ] = TypedField(
                    type=(
                        _infer_value_type(
                            value
                        )
                    ),

                    description=(
                        "Output discovered "
                        "during capability "
                        "generation."
                    ),

                    required=True,

                    # Conservative default.
                    sensitive=True,
                )

            return inferred

        # ----------------------------------------------------
        # Validate explicit schema
        # ----------------------------------------------------

        declared_names = set(
            spec.outputs
        )

        if (
            declared_names
            != discovered_names
        ):
            raise (
                CapabilityCompilationError(
                    (
                        "Declared output "
                        "schema must exactly "
                        "match discovered "
                        "outputs. "
                        f"Declared="
                        f"{sorted(declared_names)}, "
                        f"discovered="
                        f"{sorted(discovered_names)}"
                    )
                )
            )

        for (
            name,
            field,
        ) in spec.outputs.items():

            value = (
                discovery.outputs[
                    name
                ]
            )

            if not _matches_value_type(
                value,
                field.type,
            ):
                raise (
                    CapabilityCompilationError(
                        (
                            f"Output '{name}' "
                            f"declares type "
                            f"'{field.type.value}' "
                            "but discovery "
                            f"value has type "
                            f"'{type(value).__name__}'."
                        )
                    )
                )

        return spec.outputs

    # ========================================================
    # Checkpoint
    # ========================================================

    @staticmethod
    def _build_checkpoint(
        *,
        outputs: dict[
            str,
            TypedField,
        ],
        explicit: (
            Condition
            | None
        ),
    ) -> Condition:
        """
        Build the deterministic success checkpoint.

        With exactly one output, OUTPUT_EXISTS is a safe
        default.

        Multiple outputs require an explicit checkpoint.
        """

        if explicit is not None:
            return explicit

        if len(outputs) == 1:

            output_name = next(
                iter(
                    outputs
                )
            )

            return Condition(
                type=(
                    ConditionType
                    .OUTPUT_EXISTS
                ),

                output_name=(
                    output_name
                ),

                timeout_ms=0,
            )

        raise CapabilityCompilationError(
            (
                "Capability has multiple "
                "outputs and no explicit "
                "checkpoint was supplied."
            )
        )

    # ========================================================
    # Compile
    # ========================================================

    def compile(
        self,
        *,
        discovery: DiscoveryRunResult,
        spec: CapabilityCompileSpec,
    ) -> CapabilityArtifact:
        """
        Compile a completed discovery run into a reusable
        capability artifact.
        """

        # ----------------------------------------------------
        # Discovery must have succeeded
        # ----------------------------------------------------

        if (
            discovery.status
            != DiscoveryStatus.COMPLETED
        ):
            raise CapabilityCompilationError(
                (
                    "Only a completed "
                    "discovery run may be "
                    "compiled."
                )
            )

        if not discovery.steps:
            raise CapabilityCompilationError(
                (
                    "Completed discovery "
                    "contains no steps."
                )
            )

        # ----------------------------------------------------
        # Validate contract
        # ----------------------------------------------------

        self._validate_inputs(
            spec
        )

        outputs = (
            self._build_outputs(
                discovery=discovery,
                spec=spec,
            )
        )

        # Counts only input usage that actually affects
        # executable behavior.
        step_usage = {
            name: 0
            for name in spec.inputs
        }

        compiled_steps: list[
            CapabilityStep
        ] = []

        compiled_index = 1

        # ----------------------------------------------------
        # Compile discovery steps
        # ----------------------------------------------------

        for record in discovery.steps:

            # Work with a local action variable.
            action = record.action

            # ------------------------------------------------
            # COMPLETE is discovery control flow only.
            # It should not become a deterministic replay step.
            # ------------------------------------------------

            if (
                action.action
                == ActionType.COMPLETE
            ):
                continue

            # ------------------------------------------------
            # 1. Canonicalize extraction locators
            # ------------------------------------------------
            #
            # Example:
            #
            # relative_text
            # reference_text="Current Balance"
            # relation="same_row"
            # value="$8,421.22"
            #
            # becomes:
            #
            # relative_text
            # reference_text="Current Balance"
            # relation="same_row"
            # value=None
            #
            # because the balance is runtime data.
            # ------------------------------------------------

            action = (
                _canonicalize_extraction_action(
                    action=action,
                    discovery=discovery,
                )
            )

            # ------------------------------------------------
            # 2. Reject any remaining dynamic extraction
            #    locator.
            # ------------------------------------------------
            #
            # Example that must fail:
            #
            # TEXT("$8,421.22")
            #
            # because there is no reusable structural anchor.
            # ------------------------------------------------

            _assert_no_dynamic_output_locator(
                action=action,
                discovery=discovery,
            )

            # ------------------------------------------------
            # 3. Count whether capability inputs actually
            #    affect executable behavior.
            # ------------------------------------------------

            _record_executable_input_usage(
                action=action,
                inputs=spec.inputs,
                usage=step_usage,
            )

            # ------------------------------------------------
            # 4. Parameterize the CLEANED action.
            #
            # IMPORTANT:
            #
            # Use `action`, NOT `record.action`.
            #
            # `action` may now contain our canonicalized
            # extraction locator.
            # ------------------------------------------------

            raw_action = (
                action.model_dump(
                    mode="json"
                )
            )

            parameterized_data = (
                _parameterize_without_usage_check(
                    raw_action,
                    inputs=spec.inputs,
                )
            )

            parameterized_action = (
                AgentAction.model_validate(
                    parameterized_data
                )
            )

            # ------------------------------------------------
            # 5. Convert discovery success condition into
            #    replay postconditions.
            # ------------------------------------------------

            postconditions: list[
                Condition
            ] = []

            if (
                parameterized_action
                .success_condition
                is not None
            ):
                postconditions.append(
                    parameterized_action
                    .success_condition
                )

            # ------------------------------------------------
            # 6. Build reusable capability step.
            # ------------------------------------------------

            compiled_steps.append(
                CapabilityStep(
                    id=_step_id(
                        index=compiled_index,
                        action=(
                            parameterized_action
                        ),
                    ),

                    description=(
                        parameterized_action
                        .reason
                    ),

                    action=(
                        parameterized_action
                        .action
                    ),

                    target=(
                        parameterized_action
                        .target
                    ),

                    value=(
                        parameterized_action
                        .value
                    ),

                    output_name=(
                        parameterized_action
                        .output_name
                    ),

                    preconditions=[],

                    postconditions=(
                        postconditions
                    ),

                    risk_level=(
                        parameterized_action
                        .risk_hint
                    ),
                )
            )

            compiled_index += 1

        # ----------------------------------------------------
        # At least one reusable operation must exist
        # ----------------------------------------------------

        if not compiled_steps:
            raise CapabilityCompilationError(
                (
                    "Discovery produced no "
                    "reusable capability "
                    "steps."
                )
            )

        # ----------------------------------------------------
        # Every input must affect executable behavior
        # ----------------------------------------------------

        unused_inputs = [
            name
            for (
                name,
                count,
            ) in step_usage.items()
            if count == 0
        ]

        if unused_inputs:
            raise CapabilityCompilationError(
                (
                    "Declared capability "
                    "inputs were never used "
                    "by an executable step: "
                    f"{sorted(unused_inputs)}"
                )
            )

        # ----------------------------------------------------
        # Parameterize source goal metadata
        # ----------------------------------------------------

        source_goal_template = (
            _parameterize_without_usage_check(
                discovery.goal,
                inputs=spec.inputs,
            )
        )

        # ----------------------------------------------------
        # Build checkpoint
        # ----------------------------------------------------

        checkpoint = (
            self._build_checkpoint(
                outputs=outputs,
                explicit=(
                    spec.checkpoint
                ),
            )
        )

        checkpoint_data = (
            _parameterize_without_usage_check(
                checkpoint.model_dump(
                    mode="json"
                ),
                inputs=spec.inputs,
            )
        )

        checkpoint = (
            Condition.model_validate(
                checkpoint_data
            )
        )

        # ----------------------------------------------------
        # Build artifact without hash first
        # ----------------------------------------------------

        artifact = CapabilityArtifact(
            schema_version="1.0",

            identity=(
                CapabilityIdentity(
                    id=(
                        spec.capability_id
                    ),

                    name=(
                        spec.name
                    ),

                    version=(
                        spec.version
                    ),

                    description=(
                        spec.description
                    ),

                    approval_state=(
                        spec.approval_state
                    ),
                )
            ),

            target=(
                spec.target
            ),

            inputs={
                name:
                    binding.field
                for (
                    name,
                    binding,
                ) in spec.inputs.items()
            },

            outputs=outputs,

            steps=compiled_steps,

            # Runtime semantics from the vendor/application
            # profile become part of the reusable capability.
            business_outcomes=(
                self
                .application_profile
                .business_outcomes
            ),

            recoveries=(
                self
                .application_profile
                .recoveries
            ),

            failures=(
                self
                .application_profile
                .failures
            ),

            checkpoint=checkpoint,

            safety=(
                spec.safety
            ),

            discovery=(
                DiscoveryMetadata(
                    run_id=(
                        discovery.run_id
                    ),

                    discovered_at=(
                        datetime.now(
                            timezone.utc
                        )
                    ),

                    provider=(
                        discovery.provider
                    ),

                    model=(
                        discovery.model
                    ),

                    source_tenant=(
                        spec.source_tenant
                    ),

                    source_goal_template=(
                        source_goal_template
                    ),
                )
            ),

            # Filled only after all compiler safety checks.
            integrity_sha256="",
        )

        # ----------------------------------------------------
        # Sensitive runtime leak validation
        # ----------------------------------------------------

        _assert_no_sensitive_runtime_leaks(
            artifact=artifact,
            discovery=discovery,
            spec=spec,
            outputs=outputs,
        )

        # ----------------------------------------------------
        # Integrity hash
        # ----------------------------------------------------

        digest = (
            compute_artifact_integrity(
                artifact
            )
        )

        artifact = (
            artifact.model_copy(
                update={
                    "integrity_sha256":
                        digest
                }
            )
        )

        return artifact