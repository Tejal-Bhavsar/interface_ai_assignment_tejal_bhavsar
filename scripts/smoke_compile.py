from __future__ import annotations

import asyncio

from pathlib import Path

from cua.compiler import (
    CapabilityCompilationError,
    CapabilityCompileSpec,
    CapabilityCompiler,
    CompileInput,
    save_capability_artifact,
    verify_artifact_integrity,
)

from cua.discovery import (
    DiscoveryEngine,
)

from cua.discovery_evidence import (
    DiscoveryEvidenceRecorder,
)

from cua.llm import (
    create_action_provider,
)

from cua.models import (
    ActionType,
    ApprovalState,
    DiscoveryStatus,
    SafetyContract,
    TargetSpec,
    TypedField,
    ValueType,
)

from cua.playwright_surface import (
    PlaywrightSurface,
)

from cua.policy import (
    PolicyEngine,
)

from cua.profiles import (
    get_profile,
)


# ============================================================
# Paths
# ============================================================


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


CAPABILITY_PATH = (
    PROJECT_ROOT
    / "capabilities"
    / "lookup_savings_balance.v1.json"
)

POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "policy.json"
)

DISCOVERY_EVIDENCE_ROOT = (
    PROJECT_ROOT
    / "evidence"
    / "discovery"
)


# ============================================================
# Discovery configuration
# ============================================================


DISCOVERY_MEMBER_ID = "1001"


ENTRY_URL = (
    "http://127.0.0.1:8000"
    "/legacy"
)


DISCOVERY_GOAL = (
    "Look up member 1001 and return the current savings "
    "balance. Extract the balance using the output name "
    "'current_savings_balance'."
)


# ============================================================
# Capability compile specification
# ============================================================


def build_compile_spec() -> (
    CapabilityCompileSpec
):
    """
    Describe the reusable capability contract.

    The discovery used member 1001, but the reusable
    capability accepts member_id as an input.

    The compiler will replace the concrete discovery value
    with:

        {{member_id}}
    """

    return CapabilityCompileSpec(
        capability_id=(
            "lookup_savings_balance"
        ),

        name=(
            "Lookup Savings Balance"
        ),

        version="1.0.0",

        description=(
            "Look up a member in "
            "LegacyCore X and return "
            "the member's current "
            "savings account balance."
        ),

        target=TargetSpec(
            surface_type="web",

            application=(
                "LegacyCore X"
            ),

            vendor_family=(
                "legacycore-x"
            ),

            entry_point=(
                ENTRY_URL
            ),
        ),

        # ----------------------------------------------------
        # Reusable inputs
        # ----------------------------------------------------

        inputs={
            "member_id": (
                CompileInput(
                    field=TypedField(
                        type=(
                            ValueType.STRING
                        ),

                        description=(
                            "Member ID used "
                            "to locate the "
                            "member record."
                        ),

                        required=True,

                        sensitive=True,
                    ),

                    # This is ONLY the concrete value used
                    # during discovery.
                    #
                    # It must not survive in the compiled
                    # artifact.
                    example_value=(
                        DISCOVERY_MEMBER_ID
                    ),
                )
            )
        },

        # ----------------------------------------------------
        # Reusable output contract
        # ----------------------------------------------------

        outputs={
            (
                "current_savings_balance"
            ): TypedField(
                type=(
                    ValueType.STRING
                ),

                description=(
                    "Current balance of "
                    "the member's savings "
                    "account."
                ),

                required=True,

                # Financial data.
                sensitive=True,
            )
        },

        # ----------------------------------------------------
        # Capability-local safety contract
        # ----------------------------------------------------

        safety=SafetyContract(
            allowed_origins=[
                (
                    "http://127.0.0.1:"
                    "8000"
                ),
                (
                    "http://localhost:"
                    "8000"
                ),
            ],

            allowed_routes=[
                "/legacy"
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

            risky_action_mode=(
                "require_human"
            ),
        ),

        # LLM discovery does not automatically produce an
        # approved production workflow.
        approval_state=(
            ApprovalState.DRAFT
        ),

        source_tenant=(
            "demo-credit-union"
        ),
    )


# ============================================================
# Display helpers
# ============================================================


def print_discovery(
    discovery,
) -> None:

    print()
    print(
        "=" * 70
    )

    print(
        "DISCOVERY RESULT"
    )

    print(
        "=" * 70
    )

    print(
        "RUN ID:",
        discovery.run_id,
    )

    print(
        "STATUS:",
        discovery.status.value,
    )

    print(
        "MESSAGE:",
        discovery.message,
    )

    print()

    print(
        "DISCOVERY STEPS:"
    )

    for record in (
        discovery.steps
    ):

        action = (
            record.action
        )

        print(
            (
                f"{record.step_index}. "
                f"{action.action.value}"
            )
        )

        print(
            (
                "   reason: "
                f"{action.reason}"
            )
        )

        if (
            action.target
            is not None
        ):
            print(
                (
                    "   target: "
                    f"{action.target.description}"
                )
            )
            print(
        "   locators:"
    )

            for locator in (
                action.target.locators
            ):
                print(
                    (
                        "      "
                        f"{locator.model_dump(
                    mode='json',
                    exclude_none=True,
                )}"
            )
        )
    
        if (
            action.value
            is not None
        ):
            # This is a smoke/demo script running entirely
            # against synthetic demo data.
            #
            # Persistent evidence redaction is added later.
            print(
                (
                    "   value: "
                    f"{action.value}"
                )
            )

        if (
            record
            .extracted_output_name
            is not None
        ):
            print(
                (
                    "   extracted: "
                    f"{record.extracted_output_name}"
                    "="
                    f"{record.extracted_output_value}"
                )
            )

        print(
            (
                "   url: "
                f"{record.url_after}"
            )
        )

        print()

    print(
        "DISCOVERY OUTPUTS:",
        discovery.outputs,
    )


def print_capability(
    artifact,
) -> None:

    print()
    print(
        "=" * 70
    )

    print(
        "COMPILED CAPABILITY"
    )

    print(
        "=" * 70
    )

    print(
        "ID:",
        artifact.identity.id,
    )

    print(
        "NAME:",
        artifact.identity.name,
    )

    print(
        "VERSION:",
        artifact.identity.version,
    )

    print(
        "APPROVAL:",
        (
            artifact
            .identity
            .approval_state
            .value
        ),
    )

    print(
        "SCHEMA VERSION:",
        artifact.schema_version,
    )

    print(
        "INPUTS:",
        list(
            artifact.inputs.keys()
        ),
    )

    print(
        "OUTPUTS:",
        list(
            artifact.outputs.keys()
        ),
    )

    print(
        "STEPS:",
        len(
            artifact.steps
        ),
    )

    print()

    print(
        "CAPABILITY STEPS:"
    )

    for step in (
        artifact.steps
    ):

        print(
            (
                f"- {step.id}"
            )
        )

        print(
            (
                "  action: "
                f"{step.action.value}"
            )
        )

        if (
            step.target
            is not None
        ):
            print(
                (
                    "  target: "
                    f"{step.target.description}"
                )
            )

            print(
                "  locators:"
            )

            for locator in (
                step.target.locators
            ):

                print(
                    (
                        "    - "
                        f"{locator.kind.value}"
                        ": "
                        f"{locator.model_dump(
                            mode='json',
                            exclude_none=True,
                        )}"
                    )
                )

        if (
            step.value
            is not None
        ):
            print(
                (
                    "  value: "
                    f"{step.value}"
                )
            )

        if (
            step.output_name
            is not None
        ):
            print(
                (
                    "  output: "
                    f"{step.output_name}"
                )
            )

        print()

    print(
        "CHECKPOINT:",
        (
            artifact
            .checkpoint
            .model_dump(
                mode="json",
                exclude_none=True,
            )
        ),
    )

    print()

    print(
        "INTEGRITY SHA-256:",
        artifact.integrity_sha256,
    )

    print(
        "INTEGRITY VALID:",
        verify_artifact_integrity(
            artifact
        ),
    )


# ============================================================
# Leak verification
# ============================================================


def verify_no_runtime_leaks(
    *,
    artifact,
    discovery,
) -> None:
    """
    Additional smoke-test assertions.

    The compiler already performs its own safety checks.

    These assertions make the behavior visible during the
    demo.
    """

    serialized = (
        artifact.model_dump_json()
    )

    # --------------------------------------------------------
    # Discovery input must be parameterized
    # --------------------------------------------------------

    assert (
        DISCOVERY_MEMBER_ID
        not in serialized
    ), (
        "Concrete member ID leaked "
        "into capability artifact."
    )

    assert (
        "{{member_id}}"
        in serialized
    ), (
        "Expected member_id "
        "placeholder was not created."
    )

    # --------------------------------------------------------
    # Sensitive runtime outputs must not be embedded
    # --------------------------------------------------------

    for (
        output_name,
        runtime_value,
    ) in (
        discovery.outputs.items()
    ):

        if not isinstance(
            runtime_value,
            str,
        ):
            continue

        if (
            len(runtime_value)
            < 4
        ):
            continue

        assert (
            runtime_value
            not in serialized
        ), (
            "Concrete runtime output "
            f"'{output_name}' leaked "
            "into capability artifact."
        )


# ============================================================
# Main
# ============================================================


async def main() -> None:

    print(
        "=" * 70
    )

    print(
        "STEP 10 — REAL DISCOVERY "
        "→ CAPABILITY COMPILATION"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Provider
    # --------------------------------------------------------

    provider = (
        create_action_provider()
    )

    print(
        "PROVIDER:",
        provider.provider_alias,
    )

    print(
        "MODEL:",
        provider.model_name,
    )

    # --------------------------------------------------------
    # Runtime policy
    # --------------------------------------------------------

    policy = (
        PolicyEngine.from_path(
            POLICY_PATH
        )
    )

    discovery_evidence = (
        DiscoveryEvidenceRecorder(
            root=(
                DISCOVERY_EVIDENCE_ROOT
            ),
            sensitive_inputs={
                "member_id":
                    DISCOVERY_MEMBER_ID,
            },
        )
    )

    # --------------------------------------------------------
    # Live browser discovery
    # --------------------------------------------------------

    async with (
        PlaywrightSurface(
            headless=False,
            slow_mo_ms=150,
        )
    ) as surface:

        discovery_engine = (
            DiscoveryEngine(
                surface=surface,
                provider=provider,
                policy=policy,
                evidence=(
                    discovery_evidence
                ),
                max_steps=12,
            )
        )

        discovery = (
            await discovery_engine.run(
                goal=(
                    DISCOVERY_GOAL
                ),

                entry_url=(
                    ENTRY_URL
                ),
            )
        )

        print_discovery(
            discovery
        )

        (
            discovery_evidence
            .assert_values_not_persisted(
                [
                    DISCOVERY_MEMBER_ID,
                    *discovery
                    .outputs
                    .values(),
                ]
            )
        )

        print()
        print(
            "DISCOVERY EVIDENCE:"
        )
        print(
            discovery_evidence.run_dir
        )
        print(
            "DISCOVERY EVIDENCE REDACTED: ✅"
        )

        # ----------------------------------------------------
        # Only successful discovery may compile
        # ----------------------------------------------------

        if (
            discovery.status
            != DiscoveryStatus.COMPLETED
        ):
            print()
            print(
                "Compilation skipped because "
                "discovery did not complete."
            )

            return

        # ----------------------------------------------------
        # Check expected output contract
        # ----------------------------------------------------

        expected_output = (
            "current_savings_balance"
        )

        if (
            expected_output
            not in discovery.outputs
        ):
            print()
            print(
                "Compilation stopped."
            )

            print(
                (
                    "Expected discovery "
                    "output:"
                ),
                expected_output,
            )

            print(
                (
                    "Actual discovery "
                    "outputs:"
                ),
                list(
                    discovery
                    .outputs
                    .keys()
                ),
            )

            print()
            print(
                (
                    "The discovery output "
                    "contract changed. "
                    "We fail closed instead "
                    "of silently renaming it."
                )
            )

            return

        # ----------------------------------------------------
        # Compiler
        # ----------------------------------------------------

        compiler = (
            CapabilityCompiler(
                application_profile=(
                    get_profile(
                        "legacycore-x"
                    )
                )
            )
        )

        spec = (
            build_compile_spec()
        )

        try:
            artifact = (
                compiler.compile(
                    discovery=discovery,
                    spec=spec,
                )
            )

        except (
            CapabilityCompilationError
        ) as exc:

            print()
            print(
                "=" * 70
            )

            print(
                "COMPILATION REJECTED"
            )

            print(
                "=" * 70
            )

            print(
                str(
                    exc
                )
            )

            print()
            print(
                (
                    "This is a fail-closed "
                    "compiler decision. "
                    "No capability artifact "
                    "was saved."
                )
            )

            return

        # ----------------------------------------------------
        # Extra smoke validation
        # ----------------------------------------------------

        verify_no_runtime_leaks(
            artifact=artifact,
            discovery=discovery,
        )

        if not (
            verify_artifact_integrity(
                artifact
            )
        ):
            raise RuntimeError(
                (
                    "Compiled artifact "
                    "failed integrity "
                    "verification."
                )
            )

        # ----------------------------------------------------
        # Save artifact
        # ----------------------------------------------------

        saved_path = (
            save_capability_artifact(
                artifact,
                CAPABILITY_PATH,
            )
        )

        # ----------------------------------------------------
        # Display result
        # ----------------------------------------------------

        print_capability(
            artifact
        )

        print()
        print(
            "=" * 70
        )

        print(
            "SAFETY CHECKS"
        )

        print(
            "=" * 70
        )

        print(
            "Concrete member ID absent: ✅"
        )

        print(
            (
                "Concrete discovered "
                "balance absent: ✅"
            )
        )

        print(
            "member_id placeholder present: ✅"
        )

        print(
            "Integrity hash valid: ✅"
        )

        print()

        print(
            "SAVED:"
        )

        print(
            saved_path
        )

        print()

        print(
            "STEP 10 SMOKE TEST COMPLETE ✅"
        )

        # Give you a moment to visually inspect the final
        # browser page before Chromium closes.
        await surface.wait(
            2000
        )


# ============================================================
# Entry point
# ============================================================


if __name__ == "__main__":

    asyncio.run(
        main()
    )