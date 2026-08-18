from __future__ import annotations

import json
import re

from typing import Any

from pydantic import ValidationError

from cua.models import (
    ActionType,
    ConditionType,
    LocatorKind,
    RiskLevel,
)

from cua.llm.base import (
    LLMValidationError,
)

from cua.llm.schemas import (
    LLMActionProposal,
)


# ============================================================
# Allowed enum values
# ============================================================


ENUM_FIELDS: dict[
    str,
    set[str],
] = {
    "action": {
        item.value
        for item in ActionType
    },

    "risk_hint": {
        item.value
        for item in RiskLevel
    },

    "kind": {
        item.value
        for item in LocatorKind
    },

    "type": {
        item.value
        for item in ConditionType
    },

    "relation": {
        "same_row",
        "same_form",
        "same_container",
    },
}


# ============================================================
# Transport normalization
# ============================================================


def strip_outer_code_fence(
    text: str,
) -> str:
    """
    Remove an OUTER Markdown code fence only.

    Accepted examples:

        ```json
        {...}
        ```

        ```
        {...}
        ```

    We deliberately do NOT search arbitrary prose for JSON.
    """

    cleaned = text.strip()

    pattern = re.compile(
        r"^```(?:json)?\s*\n?"
        r"(?P<body>.*?)"
        r"\n?```\s*$",
        re.IGNORECASE
        | re.DOTALL,
    )

    match = pattern.match(
        cleaned
    )

    if match:
        return (
            match.group("body")
            .strip()
        )

    return cleaned


# ============================================================
# Safe enum canonicalization
# ============================================================


def _canonicalize_enum_value(
    *,
    field_name: str,
    value: Any,
) -> Any:
    """
    Canonicalize enum casing ONLY when the value is already
    a known value case-insensitively.

    Example:

        SAFE -> safe
        Fill -> fill

    But:

        maybe_safe -> stays unchanged

    and will later fail strict Pydantic validation.
    """

    if not isinstance(
        value,
        str,
    ):
        return value

    allowed = ENUM_FIELDS.get(
        field_name
    )

    if not allowed:
        return value

    lowered = value.lower()

    if lowered in allowed:
        return lowered

    return value


def canonicalize_known_enums(
    value: Any,
) -> Any:
    """
    Recursively normalize known enum-valued fields.

    This function does not:
      - add missing fields
      - invent values
      - repair arbitrary malformed JSON
      - change unknown enum values
    """

    if isinstance(
        value,
        dict,
    ):
        result: dict[
            str,
            Any,
        ] = {}

        for key, item in (
            value.items()
        ):

            normalized_item = (
                canonicalize_known_enums(
                    item
                )
            )

            result[key] = (
                _canonicalize_enum_value(
                    field_name=key,
                    value=(
                        normalized_item
                    ),
                )
            )

        return result

    if isinstance(
        value,
        list,
    ):
        return [
            canonicalize_known_enums(
                item
            )
            for item in value
        ]

    return value


# ============================================================
# Common text -> proposal boundary
# ============================================================


def parse_text_proposal(
    text: str,
) -> LLMActionProposal:
    """
    Convert provider text into our strict common proposal.

    Pipeline:

        text
          ↓
        cosmetic fence removal
          ↓
        JSON parser
          ↓
        bounded enum canonicalization
          ↓
        strict Pydantic validation

    Anything outside these narrowly-defined transformations
    fails closed.
    """

    cleaned = (
        strip_outer_code_fence(
            text
        )
    )

    try:
        raw = json.loads(
            cleaned
        )

    except json.JSONDecodeError as exc:
        raise LLMValidationError(
            (
                "LLM response was not "
                "valid JSON."
            )
        ) from exc

    normalized = (
        canonicalize_known_enums(
            raw
        )
    )

    try:
        return (
            LLMActionProposal
            .model_validate(
                normalized
            )
        )

    except ValidationError as exc:
        raise LLMValidationError(
            (
                "LLM response did not "
                "match the required "
                "action schema: "
                f"{exc}"
            )
        ) from exc