from __future__ import annotations

import re

from collections.abc import (
    Mapping,
    Sequence,
)
from typing import Any
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from pydantic import BaseModel


REDACTED = "[REDACTED]"

SENSITIVE_DOM_SELECTOR = (
    '[data-sensitive="true"]'
)


DEFAULT_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set_cookie",
    "member_id",
    "member_name",
    "account_number",
    "routing_number",
    "ssn",
    "social_security_number",
    "balance",
    "current_balance",
}


SECRET_PATTERNS: list[
    tuple[re.Pattern[str], str]
] = [
    (
        re.compile(
            r"(?i)"
            r"(authorization\s*:\s*bearer\s+)"
            r"[^\s,;]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)"
            r"(api[_-]?key\s*[=:]\s*)"
            r"[^\s,;]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)"
            r"(password\s*[=:]\s*)"
            r"[^\s,;]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)"
            r"(access[_-]?token\s*[=:]\s*)"
            r"[^\s,;]+"
        ),
        r"\1[REDACTED]",
    ),
]


SENSITIVE_ELEMENT_PATTERN = re.compile(
    r"""
    (
        <
        (?P<tag>[a-zA-Z][a-zA-Z0-9]*)
        \b
        [^>]*
        data-sensitive
        \s*=\s*
        ["']
        true
        ["']
        [^>]*
        >
    )
    .*?
    (
        </(?P=tag)>
    )
    """,
    re.IGNORECASE
    | re.DOTALL
    | re.VERBOSE,
)


SENSITIVE_INPUT_VALUE_PATTERN = re.compile(
    r"""
    (
        <
        input
        \b
        (?=[^>]*data-sensitive\s*=\s*["']true["'])
        [^>]*?
        \bvalue\s*=\s*
        ["']
    )
    [^"']*
    (
        ["']
        [^>]*
        >
    )
    """,
    re.IGNORECASE
    | re.VERBOSE,
)


def normalize_key(
    key: str,
) -> str:

    return (
        key.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def is_sensitive_key(
    key: str,
    sensitive_keys: set[str] | None = None,
) -> bool:

    keys = (
        sensitive_keys
        or DEFAULT_SENSITIVE_KEYS
    )

    normalized = normalize_key(key)

    if normalized in keys:
        return True

    sensitive_fragments = (
        "password",
        "secret",
        "token",
        "api_key",
        "authorization",
        "cookie",
        "member_id",
        "account_number",
        "routing_number",
        "ssn",
    )

    return any(
        fragment in normalized
        for fragment
        in sensitive_fragments
    )


def redact_text(
    value: str,
) -> str:

    result = value

    for pattern, replacement in (
        SECRET_PATTERNS
    ):
        result = pattern.sub(
            replacement,
            result,
        )

    return result


def redact_known_values(
    text: str,
    sensitive_values: set[str] | None,
) -> str:

    if not sensitive_values:
        return text

    result = text

    ordered_values = sorted(
        (
            value
            for value in sensitive_values
            if value
        ),
        key=len,
        reverse=True,
    )

    for value in ordered_values:
        result = result.replace(
            value,
            REDACTED,
        )

    return result


def redact_url(
    url: str,
    sensitive_keys: set[str] | None = None,
) -> str:

    try:
        parts = urlsplit(url)

        query_items = parse_qsl(
            parts.query,
            keep_blank_values=True,
        )

        redacted_query: list[
            tuple[str, str]
        ] = []

        for key, value in query_items:

            if is_sensitive_key(
                key,
                sensitive_keys,
            ):
                value = REDACTED

            redacted_query.append(
                (key, value)
            )

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(
                    redacted_query
                ),
                parts.fragment,
            )
        )

    except ValueError:
        return redact_text(url)


def redact_data(
    value: Any,
    *,
    sensitive_keys: set[str] | None = None,
    sensitive_values: set[str] | None = None,
) -> Any:

    if isinstance(
        value,
        Mapping,
    ):

        result: dict[str, Any] = {}

        for key, item in value.items():

            key_string = str(key)

            if is_sensitive_key(
                key_string,
                sensitive_keys,
            ):
                result[key_string] = (
                    REDACTED
                )

            else:
                result[key_string] = (
                    redact_data(
                        item,
                        sensitive_keys=(
                            sensitive_keys
                        ),
                        sensitive_values=(
                            sensitive_values
                        ),
                    )
                )

        return result

    if isinstance(
        value,
        BaseModel,
    ):

        return redact_data(
            value.model_dump(
                mode="json"
            ),
            sensitive_keys=(
                sensitive_keys
            ),
            sensitive_values=(
                sensitive_values
            ),
        )

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):

        return [
            redact_data(
                item,
                sensitive_keys=(
                    sensitive_keys
                ),
                sensitive_values=(
                    sensitive_values
                ),
            )
            for item in value
        ]

    if isinstance(
        value,
        str,
    ):

        result = redact_text(
            value
        )

        result = redact_known_values(
            result,
            sensitive_values,
        )

        return result

    return value


def collect_sensitive_input_values(
    inputs: Mapping[str, Any],
    input_schema: Mapping[str, Any],
) -> set[str]:

    values: set[str] = set()

    for name, field in (
        input_schema.items()
    ):

        sensitive = getattr(
            field,
            "sensitive",
            False,
        )

        if (
            sensitive
            and name in inputs
            and inputs[name] is not None
        ):
            values.add(
                str(inputs[name])
            )

    return values


def redact_dom_html(
    html: str,
    *,
    sensitive_values: set[str] | None = None,
) -> str:

    result = (
        SENSITIVE_INPUT_VALUE_PATTERN.sub(
            rf"\1{REDACTED}\2",
            html,
        )
    )

    def replace_element(
        match: re.Match[str],
    ) -> str:

        opening = match.group(1)
        closing = match.group(3)

        return (
            f"{opening}"
            f"{REDACTED}"
            f"{closing}"
        )

    result = (
        SENSITIVE_ELEMENT_PATTERN.sub(
            replace_element,
            result,
        )
    )

    result = redact_text(
        result
    )

    result = redact_known_values(
        result,
        sensitive_values,
    )

    return result


class Redactor:

    def __init__(
        self,
        *,
        sensitive_keys: set[str] | None = None,
        sensitive_values: set[str] | None = None,
    ):

        self.sensitive_keys = (
            sensitive_keys
            or DEFAULT_SENSITIVE_KEYS
        )

        self.sensitive_values = (
            sensitive_values
            or set()
        )

    def text(
        self,
        value: str,
    ) -> str:

        result = redact_text(
            value
        )

        return redact_known_values(
            result,
            self.sensitive_values,
        )

    def data(
        self,
        value: Any,
    ) -> Any:

        return redact_data(
            value,
            sensitive_keys=(
                self.sensitive_keys
            ),
            sensitive_values=(
                self.sensitive_values
            ),
        )

    def url(
        self,
        value: str,
    ) -> str:

        result = redact_url(
            value,
            self.sensitive_keys,
        )

        return redact_known_values(
            result,
            self.sensitive_values,
        )

    def dom(
        self,
        html: str,
    ) -> str:

        return redact_dom_html(
            html,
            sensitive_values=(
                self.sensitive_values
            ),
        )