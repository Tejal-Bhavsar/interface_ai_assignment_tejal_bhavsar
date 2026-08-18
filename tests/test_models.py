from cua.models import (
    ActionType,
    LocatorCandidate,
    LocatorKind,
    TargetDescriptor,
    TypedField,
    ValueType,
)


def test_locator_candidate_serializes():
    locator = LocatorCandidate(
        kind=LocatorKind.ROLE,
        role="button",
        name="Search",
    )

    data = locator.model_dump()

    assert data["kind"] == "role"
    assert data["role"] == "button"
    assert data["name"] == "Search"


def test_sensitive_input_field():
    field = TypedField(
        type=ValueType.STRING,
        description="Member identifier",
        sensitive=True,
    )

    assert field.sensitive is True


def test_target_can_have_fallback_locators():
    target = TargetDescriptor(
        description="Member search button",
        locators=[
            LocatorCandidate(
                kind=LocatorKind.ROLE,
                role="button",
                name="Search",
            ),
            LocatorCandidate(
                kind=LocatorKind.TEXT,
                value="Search",
            ),
        ],
    )

    assert len(target.locators) == 2
    assert target.locators[0].kind == LocatorKind.ROLE
    assert target.locators[1].kind == LocatorKind.TEXT


def test_invalid_action_type_is_rejected():
    valid_actions = {
        action.value
        for action in ActionType
    }

    assert "click" in valid_actions
    assert "random_shell_command" not in valid_actions