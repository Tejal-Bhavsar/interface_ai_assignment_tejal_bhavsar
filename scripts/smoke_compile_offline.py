from __future__ import annotations

from pathlib import Path

from cua.compiler import (
    CapabilityCompileSpec,
    CapabilityCompiler,
    CompileInput,
    save_capability_artifact,
    verify_artifact_integrity,
)

from cua.models import (
    ActionType,
    AgentAction,
    ApprovalState,
    DiscoveryRunResult,
    DiscoveryStatus,
    DiscoveryStepRecord,
    LocatorCandidate,
    LocatorKind,
    RiskLevel,
    SafetyContract,
    TargetDescriptor,
    TargetSpec,
    TypedField,
    ValueType,
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
    / ("lookup_savings_balance"
       ".offline.v1.json")
)


# ============================================================
# Demo runtime values
# ============================================================


DISCOVERY_MEMBER_ID = "1001"

DISCOVERED_BALANCE = "$8,421.22"

ENTRY_URL = (
    "http://127.0.0.1:8000"
    "/legacy"
)


# ============================================================
# Stable target helpers
# ============================================================


def member_id_target() -> (
    TargetDescriptor
):
    """
    Stable locator for the member ID field.
    """

    return TargetDescriptor(
        description=(
            "Member ID textbox"
        ),

        locators=[
            LocatorCandidate(
                kind=(
                    LocatorKind.ROLE
                ),

                role="textbox",

                name="Member ID",

                exact=True,

                description=(
                    "Member ID textbox"
                ),
            ),

            LocatorCandidate(
                kind=(
                    LocatorKind.LABEL
                ),

                value="Member ID",

                exact=True,

                description=(
                    "Member ID field "
                    "located by label"
                ),
            ),
        ],
    )


def search_button_target() -> (
    TargetDescriptor
):
    """
    Stable semantic locator for Search.
    """

    return TargetDescriptor(
        description=(
            "Search button"
        ),

        locators=[
            LocatorCandidate(
                kind=(
                    LocatorKind.ROLE
                ),

                role="button",

                name="Search",

                exact=True,

                description=(
                    "Search button"
                ),
            )
        ],
    )


def savings_link_target() -> (
    TargetDescriptor
):
    """
    Stable locator for the member's Savings link.

    Notice that it does not contain member-specific data.
    """

    return TargetDescriptor(
        description=(
            "Savings account link"
        ),

        locators=[
            LocatorCandidate(
                kind=(
                    LocatorKind.ROLE
                ),

                role="link",

                name="Savings",

                exact=True,

                description=(
                    "Savings account link"
                ),
            ),

            LocatorCandidate(
                kind=(
                    LocatorKind.TEXT
                ),

                value="Savings",

                exact=True,

                description=(
                    "Savings link text"
                ),
            ),
        ],
    )


def current_balance_target() -> (
    TargetDescriptor
):
    """
    Stable structural locator for the balance.

    IMPORTANT:

    We deliberately do NOT use:

        text="$8,421.22"

    because the actual balance is runtime data.

    Instead we locate the value relative to the stable
    "Current Balance" label.
    """

    return TargetDescriptor(
        description=(
            "Current Balance value"
        ),

        locators=[
            LocatorCandidate(
                kind=(
                    LocatorKind
                    .RELATIVE_TEXT
                ),

                reference_text=(
                    "Current Balance"
                ),

                relation=(
                    "same_row"
                ),

                exact=True,

                description=(
                    "Value in the same "
                    "row as Current Balance"
                ),
            )
        ],
    )


# ============================================================
# Offline discovery fixture
# ============================================================


def build_offline_discovery() -> (
    DiscoveryRunResult
):
    """
    Create the deterministic equivalent of the genuine
    discovery workflow we already observed.

    No model is called here.

    This exists only to test Step 10 independently from
    provider quota/network availability.
    """

    legacy_url = ENTRY_URL

    member_url = (
        "http://127.0.0.1:8000"
        "/legacy/member/1001"
    )

    savings_url = (
        "http://127.0.0.1:8000"
        "/legacy/member/1001"
        "/account/savings"
    )

    return DiscoveryRunResult(
        run_id=(
            "disc_offline_step10"
        ),

        goal=(
            "Look up member 1001 "
            "and return the current "
            "savings balance."
        ),

        entry_url=(
            ENTRY_URL
        ),

        # Explicitly identify this as an offline fixture.
        # We are NOT pretending it was another genuine
        # model run.
        provider=(
            "offline-fixture"
        ),

        model=(
            "none"
        ),

        status=(
            DiscoveryStatus.COMPLETED
        ),

        steps=[

            # =================================================
            # 1. Fill Member ID
            # =================================================

            DiscoveryStepRecord(
                step_index=1,

                url_before=(
                    legacy_url
                ),

                url_after=(
                    legacy_url
                ),

                action=AgentAction(
                    action=(
                        ActionType.FILL
                    ),

                    target=(
                        member_id_target()
                    ),

                    value=(
                        DISCOVERY_MEMBER_ID
                    ),

                    reason=(
                        "Fill the Member ID "
                        "field with the "
                        "provided member ID."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),

            # =================================================
            # 2. Search
            # =================================================

            DiscoveryStepRecord(
                step_index=2,

                url_before=(
                    legacy_url
                ),

                url_after=(
                    member_url
                ),

                action=AgentAction(
                    action=(
                        ActionType.CLICK
                    ),

                    target=(
                        search_button_target()
                    ),

                    reason=(
                        "Click Search to "
                        "look up the member."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),

            # =================================================
            # 3. Open Savings
            # =================================================

            DiscoveryStepRecord(
                step_index=3,

                url_before=(
                    member_url
                ),

                url_after=(
                    savings_url
                ),

                action=AgentAction(
                    action=(
                        ActionType.CLICK
                    ),

                    target=(
                        savings_link_target()
                    ),

                    reason=(
                        "Open the member's "
                        "Savings account."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),

            # =================================================
            # 4. Extract Balance
            # =================================================

            DiscoveryStepRecord(
                step_index=4,

                url_before=(
                    savings_url
                ),

                url_after=(
                    savings_url
                ),

                action=AgentAction(
                    action=(
                        ActionType.EXTRACT
                    ),

                    target=(
                        current_balance_target()
                    ),

                    output_name=(
                        "current_savings_balance"
                    ),

                    reason=(
                        "Extract the value "
                        "associated with "
                        "Current Balance."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),

                extracted_output_name=(
                    "current_savings_balance"
                ),

                extracted_output_value=(
                    DISCOVERED_BALANCE
                ),
            ),

            # =================================================
            # 5. Discovery complete
            # =================================================

            DiscoveryStepRecord(
                step_index=5,

                url_before=(
                    savings_url
                ),

                url_after=(
                    savings_url
                ),

                action=AgentAction(
                    action=(
                        ActionType.COMPLETE
                    ),

                    reason=(
                        "The requested "
                        "savings balance "
                        "has been extracted."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),
        ],

        outputs={
            (
                "current_savings_balance"
            ): DISCOVERED_BALANCE
        },

        message=(
            "Offline deterministic "
            "discovery fixture completed."
        ),
    )


# ============================================================
# Compile specification
# ============================================================


def build_compile_spec() -> (
    CapabilityCompileSpec
):

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
            "savings balance."
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

        # ====================================================
        # Typed reusable input
        # ====================================================

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

                    # Concrete value from the discovery run.
                    #
                    # The compiler must replace this with:
                    #
                    #     {{member_id}}
                    #
                    example_value=(
                        DISCOVERY_MEMBER_ID
                    ),
                )
            )
        },

        # ====================================================
        # Typed reusable output
        # ====================================================

        outputs={
            (
                "current_savings_balance"
            ): TypedField(
                type=(
                    ValueType.STRING
                ),

                description=(
                    "Current savings "
                    "account balance."
                ),

                required=True,

                sensitive=True,
            )
        },

        # ====================================================
        # Capability safety contract
        # ====================================================

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

        # A discovered capability starts as draft.
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
    discovery: DiscoveryRunResult,
) -> None:

    print()
    print(
        "=" * 70
    )

    print(
        "OFFLINE DISCOVERY FIXTURE"
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
        "PROVIDER:",
        discovery.provider,
    )

    print(
        "MODEL:",
        discovery.model,
    )

    print()

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
                    "      ",
                    locator.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                )

        if (
            action.value
            is not None
        ):
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

        print()


def print_artifact(
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
        "PARAMETERIZED STEPS:"
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

            for locator in (
                step.target.locators
            ):

                print(
                    (
                        "    locator: "
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
        artifact.checkpoint.model_dump(
            mode="json",
            exclude_none=True,
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
# Offline smoke assertions
# ============================================================


def verify_compiled_artifact(
    *,
    artifact,
) -> None:
    """
    Prove that discovery-specific runtime data did not become
    part of the reusable capability.
    """

    raw = (
        artifact.model_dump_json()
    )

    # --------------------------------------------------------
    # Member ID must disappear
    # --------------------------------------------------------

    assert (
        DISCOVERY_MEMBER_ID
        not in raw
    ), (
        "Concrete discovery member ID "
        "remained in the artifact."
    )

    # --------------------------------------------------------
    # Parameter must exist
    # --------------------------------------------------------

    assert (
        "{{member_id}}"
        in raw
    ), (
        "member_id was not "
        "parameterized."
    )

    # --------------------------------------------------------
    # Balance must disappear
    # --------------------------------------------------------

    assert (
        DISCOVERED_BALANCE
        not in raw
    ), (
        "Concrete discovery balance "
        "remained in the artifact."
    )

    # --------------------------------------------------------
    # No COMPLETE step
    # --------------------------------------------------------

    assert all(
        step.action
        != ActionType.COMPLETE
        for step
        in artifact.steps
    )

    # --------------------------------------------------------
    # Expected number of reusable operations
    # --------------------------------------------------------

    assert len(
        artifact.steps
    ) == 4

    # --------------------------------------------------------
    # Integrity
    # --------------------------------------------------------

    assert (
        verify_artifact_integrity(
            artifact
        )
        is True
    )


# ============================================================
# Main
# ============================================================


def main() -> None:

    print(
        "=" * 70
    )

    print(
        "STEP 10 — OFFLINE "
        "CAPABILITY COMPILER SMOKE TEST"
    )

    print(
        "=" * 70
    )

    print(
        "LLM CALLS: 0"
    )

    print(
        "NETWORK CALLS: 0"
    )

    # --------------------------------------------------------
    # Build deterministic discovery fixture
    # --------------------------------------------------------

    discovery = (
        build_offline_discovery()
    )

    print_discovery(
        discovery
    )

    # --------------------------------------------------------
    # Real compiler
    # --------------------------------------------------------

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

    artifact = (
        compiler.compile(
            discovery=discovery,
            spec=spec,
        )
    )

    # --------------------------------------------------------
    # Validate artifact
    # --------------------------------------------------------

    verify_compiled_artifact(
        artifact=artifact
    )

    # --------------------------------------------------------
    # Save actual capability JSON
    # --------------------------------------------------------

    saved_path = (
        save_capability_artifact(
            artifact,
            CAPABILITY_PATH,
        )
    )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print_artifact(
        artifact
    )

    print()
    print(
        "=" * 70
    )

    print(
        "OFFLINE SAFETY CHECKS"
    )

    print(
        "=" * 70
    )

    print(
        "No LLM used: ✅"
    )

    print(
        "Concrete member ID removed: ✅"
    )

    print(
        "Concrete balance removed: ✅"
    )

    print(
        "{{member_id}} present: ✅"
    )

    print(
        "COMPLETE step removed: ✅"
    )

    print(
        "Integrity valid: ✅"
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
        "STEP 10 OFFLINE SMOKE "
        "TEST COMPLETE ✅"
    )


# ============================================================
# Entry point
# ============================================================


if __name__ == "__main__":

    main()