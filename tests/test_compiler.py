import pytest

from cua.compiler import (
    CapabilityCompilationError,
    CapabilityCompileSpec,
    CapabilityCompiler,
    CompileInput,
    capability_placeholder,
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


def member_input_target():
    return TargetDescriptor(
        description=(
            "Member ID textbox"
        ),
        locators=[
            LocatorCandidate(
                kind=LocatorKind.ROLE,
                role="textbox",
                name="Member ID",
            ),
            LocatorCandidate(
                kind=LocatorKind.LABEL,
                value="Member ID",
            ),
        ],
    )


def search_target():
    return TargetDescriptor(
        description="Search button",
        locators=[
            LocatorCandidate(
                kind=LocatorKind.ROLE,
                role="button",
                name="Search",
            )
        ],
    )


def savings_target():
    return TargetDescriptor(
        description=(
            "Savings account link"
        ),
        locators=[
            LocatorCandidate(
                kind=LocatorKind.TEXT,
                value="Savings",
            )
        ],
    )


def balance_target():
    return TargetDescriptor(
        description=(
            "Current Balance value"
        ),
        locators=[
            LocatorCandidate(
                kind=LocatorKind.CSS,
                value=(
                    "tr:has-text('Current Balance') "
                    "td[data-sensitive='true']"
                ),
                description=(
                    "Balance cell in the "
                    "Current Balance row"
                ),
            )
        ],
    )

def test_sensitive_runtime_output_leak_is_rejected():

    discovery = make_discovery()

    # Use a stable extraction locator.
    discovery.steps[
        3
    ].action.target = (
        TargetDescriptor(
            description=(
                "Current Balance "
                "$8,421.22"
            ),

            locators=[
                LocatorCandidate(
                    kind=(
                        LocatorKind.RELATIVE_TEXT
                    ),

                    value=None,

                    reference_text=(
                        "Current Balance"
                    ),

                    relation=(
                        "same_row"
                    ),

                    exact=True,
                )
            ],
        )
    )

    with pytest.raises(
        CapabilityCompilationError,
        match=(
            "Sensitive runtime "
            "output value"
        ),
    ):
        make_compiler().compile(
            discovery=discovery,
            spec=make_spec(),
        )


def test_relative_extract_runtime_value_is_canonicalized():

    discovery = (
        make_discovery()
    )

    discovery.steps[
        3
    ].action.target = (
        TargetDescriptor(
            description=(
                "Current Balance value"
            ),

            locators=[
                LocatorCandidate(
                    kind=(
                        LocatorKind
                        .RELATIVE_TEXT
                    ),

                    value=(
                        "$8,421.22"
                    ),

                    reference_text=(
                        "Current Balance"
                    ),

                    relation=(
                        "same_row"
                    ),

                    exact=True,

                    description=(
                        "Balance value "
                        "associated with "
                        "Current Balance"
                    ),
                )
            ],
        )
    )

    artifact = (
        make_compiler()
        .compile(
            discovery=discovery,
            spec=make_spec(),
        )
    )

    extract_step = (
        artifact.steps[3]
    )

    locator = (
        extract_step
        .target
        .locators[0]
    )

    assert (
        locator.kind
        == LocatorKind.RELATIVE_TEXT
    )

    assert (
        locator.reference_text
        == "Current Balance"
    )

    assert (
        locator.relation
        == "same_row"
    )

    # The discovery-specific balance must disappear.
    assert (
        locator.value
        is None
    )

    raw = (
        artifact.model_dump_json()
    )

    assert (
        "$8,421.22"
        not in raw
    )
        
def make_discovery(
    *,
    status=(
        DiscoveryStatus.COMPLETED
    ),
):
    return DiscoveryRunResult(
        run_id="disc_test123",

        goal=(
            "Look up member 1001 "
            "and return the current "
            "savings balance."
        ),

        entry_url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),

        provider="gemini",

        model="gemini-2.5-flash",

        status=status,

        steps=[
            DiscoveryStepRecord(
                step_index=1,

                url_before=(
                    "http://127.0.0.1:"
                    "8000/legacy"
                ),

                action=AgentAction(
                    action=(
                        ActionType.FILL
                    ),

                    target=(
                        member_input_target()
                    ),

                    value="1001",

                    reason=(
                        "Fill member ID "
                        "1001."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),

            DiscoveryStepRecord(
                step_index=2,

                url_before=(
                    "http://127.0.0.1:"
                    "8000/legacy"
                ),

                action=AgentAction(
                    action=(
                        ActionType.CLICK
                    ),

                    target=(
                        search_target()
                    ),

                    reason=(
                        "Search for member."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),

            DiscoveryStepRecord(
                step_index=3,

                url_before=(
                    "http://127.0.0.1:"
                    "8000/legacy/member/"
                    "1001"
                ),

                action=AgentAction(
                    action=(
                        ActionType.CLICK
                    ),

                    target=(
                        savings_target()
                    ),

                    reason=(
                        "Open Savings."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),

            DiscoveryStepRecord(
                step_index=4,

                url_before=(
                    "http://127.0.0.1:"
                    "8000/legacy/member/"
                    "1001/account/savings"
                ),

                action=AgentAction(
                    action=(
                        ActionType.EXTRACT
                    ),

                    target=(
                        balance_target()
                    ),

                    output_name=(
                        "current_savings_balance"
                    ),

                    reason=(
                        "Extract current "
                        "savings balance."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),

                extracted_output_name=(
                    "current_savings_balance"
                ),

                extracted_output_value=(
                    "$8,421.22"
                ),
            ),

            DiscoveryStepRecord(
                step_index=5,

                url_before=(
                    "http://127.0.0.1:"
                    "8000/legacy/member/"
                    "1001/account/savings"
                ),

                action=AgentAction(
                    action=(
                        ActionType.COMPLETE
                    ),

                    reason=(
                        "Balance retrieved."
                    ),

                    risk_hint=(
                        RiskLevel.SAFE
                    ),
                ),
            ),
        ],

        outputs={
            "current_savings_balance":
                "$8,421.22"
        },

        message=(
            "Discovery completed "
            "successfully."
        ),
    )


def make_spec(
    *,
    example_member_id="1001",
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
            "Look up a member and "
            "return the current "
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
                "http://127.0.0.1:"
                "8000/legacy"
            ),
        ),

        inputs={
            "member_id": CompileInput(
                field=TypedField(
                    type=(
                        ValueType.STRING
                    ),

                    description=(
                        "Bank or credit "
                        "union member ID."
                    ),

                    required=True,

                    sensitive=True,
                ),

                example_value=(
                    example_member_id
                ),
            )
        },

        outputs={
            "current_savings_balance":
                TypedField(
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

        safety=SafetyContract(
            allowed_origins=[
                (
                    "http://127.0.0.1:"
                    "8000"
                )
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

        approval_state=(
            ApprovalState.DRAFT
        ),

        source_tenant=(
            "demo-credit-union"
        ),
    )


def make_compiler():
    return CapabilityCompiler(
        application_profile=(
            get_profile(
                "legacycore-x"
            )
        )
    )


def test_compile_successful_discovery():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    assert (
        artifact.identity.id
        == "lookup_savings_balance"
    )

    assert (
        artifact.identity.version
        == "1.0.0"
    )

    assert (
        artifact.identity
        .approval_state
        == ApprovalState.DRAFT
    )


def test_concrete_input_is_parameterized():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    assert (
        artifact.steps[0].value
        == capability_placeholder(
            "member_id"
        )
    )

    assert (
        "{{member_id}}"
        in (
            artifact
            .discovery
            .source_goal_template
        )
    )


def test_sensitive_runtime_values_not_saved():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    raw = (
        artifact.model_dump_json()
    )

    assert "1001" not in raw

    assert "$8,421.22" not in raw


def test_complete_is_not_capability_step():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    assert len(
        artifact.steps
    ) == 4

    assert all(
        step.action
        != ActionType.COMPLETE
        for step
        in artifact.steps
    )


def test_default_checkpoint_is_output_exists():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    assert (
        artifact.checkpoint.type.value
        == "output_exists"
    )

    assert (
        artifact.checkpoint
        .output_name
        == "current_savings_balance"
    )


def test_application_profile_is_embedded():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    assert (
        len(
            artifact.business_outcomes
        )
        > 0
    )

    assert (
        len(
            artifact.recoveries
        )
        > 0
    )

    assert (
        len(
            artifact.failures
        )
        > 0
    )

def test_dynamic_extract_text_locator_is_rejected():

    discovery = (
        make_discovery()
    )

    discovery.steps[
        3
    ].action.target = (
        TargetDescriptor(
            description=(
                "Current Balance"
            ),

            locators=[
                LocatorCandidate(
                    kind=(
                        LocatorKind.TEXT
                    ),

                    value=(
                        "$8,421.22"
                    ),
                )
            ],
        )
    )

    with pytest.raises(
        CapabilityCompilationError,
        match=(
            "Dynamic extraction"
        ),
    ):
        make_compiler().compile(
            discovery=discovery,
            spec=make_spec(),
        )

def test_integrity_hash_is_valid():

    artifact = (
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),
            spec=make_spec(),
        )
    )

    assert (
        len(
            artifact.integrity_sha256
        )
        == 64
    )

    assert (
        verify_artifact_integrity(
            artifact
        )
        is True
    )


def test_non_completed_discovery_rejected():

    discovery = make_discovery(
        status=(
            DiscoveryStatus.FAILED
        )
    )

    with pytest.raises(
        CapabilityCompilationError
    ):
        make_compiler().compile(
            discovery=discovery,
            spec=make_spec(),
        )


def test_unused_declared_input_rejected():

    with pytest.raises(
        CapabilityCompilationError,
        match="never used",
    ):
        make_compiler().compile(
            discovery=(
                make_discovery()
            ),

            spec=make_spec(
                example_member_id=(
                    "9999"
                )
            ),
        )