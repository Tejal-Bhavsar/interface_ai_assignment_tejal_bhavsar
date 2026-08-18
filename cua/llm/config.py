from __future__ import annotations

import json

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DEFAULT_LLM_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "llm.json"
)


class ProviderType(
    str,
    Enum,
):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROK = "grok"
    OLLAMA = "ollama"

    OPENAI_COMPATIBLE = (
        "openai_compatible"
    )

    MOCK = "mock"


class ProviderConfig(
    BaseModel
):
    type: ProviderType

    model: str

    enabled: bool = True

    api_key_env: str | None = None

    base_url: str | None = None

    timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=600,
    )

    max_output_tokens: int = Field(
        default=1200,
        ge=128,
        le=8192,
    )

    options: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict
    )


class LLMConfig(
    BaseModel
):
    active_provider: str

    providers: dict[
        str,
        ProviderConfig,
    ]

    @model_validator(
        mode="after"
    )
    def validate_active_provider(
        self,
    ) -> "LLMConfig":

        selected = (
            self.providers.get(
                self.active_provider
            )
        )

        if selected is None:
            raise ValueError(
                (
                    f"Active provider "
                    f"'{self.active_provider}' "
                    f"is not configured."
                )
            )

        if not selected.enabled:
            raise ValueError(
                (
                    f"Active provider "
                    f"'{self.active_provider}' "
                    f"is disabled."
                )
            )

        return self


def load_llm_config(
    path: Path | str = (
        DEFAULT_LLM_CONFIG_PATH
    ),
) -> LLMConfig:

    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            (
                "LLM config file not "
                f"found: {config_path}"
            )
        )

    raw = json.loads(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    return LLMConfig.model_validate(
        raw
    )