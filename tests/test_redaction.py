from cua.models import (
    TypedField,
    ValueType,
)

from cua.redaction import (
    REDACTED,
    Redactor,
    collect_sensitive_input_values,
    is_sensitive_key,
    redact_data,
    redact_dom_html,
    redact_text,
)


def test_sensitive_key_detection():
    assert (
        is_sensitive_key(
            "member_id"
        )
        is True
    )

    assert (
        is_sensitive_key(
            "access_token"
        )
        is True
    )

    assert (
        is_sensitive_key(
            "step_number"
        )
        is False
    )


def test_sensitive_dictionary_values_are_redacted():
    value = {
        "member_id": "1001",
        "action": "search",
    }

    result = redact_data(
        value
    )

    assert (
        result["member_id"]
        == REDACTED
    )

    assert (
        result["action"]
        == "search"
    )


def test_nested_sensitive_data_is_redacted():
    value = {
        "request": {
            "password": "super-secret",
            "operation": "login",
        }
    }

    result = redact_data(
        value
    )

    assert (
        result["request"]["password"]
        == REDACTED
    )

    assert (
        result["request"]["operation"]
        == "login"
    )


def test_bearer_token_is_redacted_from_text():
    text = (
        "Authorization: Bearer abc123"
    )

    result = redact_text(
        text
    )

    assert "abc123" not in result

    assert REDACTED in result


def test_known_runtime_value_is_removed():
    redactor = Redactor(
        sensitive_values={
            "1001",
        }
    )

    result = redactor.text(
        (
            "Opening member 1001 "
            "account page."
        )
    )

    assert "1001" not in result

    assert REDACTED in result


def test_sensitive_member_id_in_url_path_is_removed():
    redactor = Redactor(
        sensitive_values={
            "1001",
        }
    )

    result = redactor.url(
        (
            "http://localhost:8000/"
            "legacy/member/1001"
        )
    )

    assert "1001" not in result

    assert REDACTED in result


def test_sensitive_query_parameter_is_redacted():
    redactor = Redactor()

    result = redactor.url(
        (
            "http://localhost:8000/"
            "legacy?member_id=1001"
        )
    )

    assert "1001" not in result


def test_collect_sensitive_values_from_schema():
    input_schema = {
        "member_id": TypedField(
            type=ValueType.STRING,
            description="Member identifier",
            sensitive=True,
        ),
        "account_type": TypedField(
            type=ValueType.STRING,
            description="Account type",
            sensitive=False,
        ),
    }

    inputs = {
        "member_id": "1001",
        "account_type": "savings",
    }

    values = (
        collect_sensitive_input_values(
            inputs,
            input_schema,
        )
    )

    assert "1001" in values

    assert "savings" not in values


def test_sensitive_dom_content_is_redacted():
    html = """
    <table>
        <tr>
            <td data-sensitive="true">
                Alex Rivera
            </td>
        </tr>
    </table>
    """

    result = redact_dom_html(
        html
    )

    assert "Alex Rivera" not in result

    assert REDACTED in result


def test_sensitive_input_value_is_redacted():
    html = """
    <input
        data-sensitive="true"
        value="1001"
    />
    """

    result = redact_dom_html(
        html
    )

    assert "1001" not in result

    assert REDACTED in result