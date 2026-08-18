from __future__ import annotations

import os

from pathlib import Path

from dotenv import load_dotenv

from cua.llm.anthropic_provider import (
    AnthropicProvider,
)

from cua.llm.base import (
    ActionProvider,
    LLMConfigurationError,
)

from cua.llm.config import (
    DEFAULT_LLM_CONFIG_PATH,
    ProviderType,
    load_llm_config,
)

from cua.llm.gemini_provider import (
    GeminiProvider,
)

from cua.llm.grok_provider import (
    GrokProvider,
)

from cua.llm.mock_provider import (
    MockActionProvider,
)

from cua.llm.ollama_provider import (
    OllamaProvider,
)

from cua.llm.openai_compatible_provider import (
    OpenAICompatibleProvider,
)

from cua.llm.openai_provider import (
    OpenAIProvider,
)


def create_action_provider(
    *,
    path: Path | str = (
        DEFAULT_LLM_CONFIG_PATH
    ),
    provider_name: str | None = None,
) -> ActionProvider:

    load_dotenv()

    config = load_llm_config(
        path
    )

    selected_name = (
        provider_name
        or os.getenv(
            "CUA_LLM_PROVIDER"
        )
        or config.active_provider
    )

    provider_config = (
        config.providers.get(
            selected_name
        )
    )

    if provider_config is None:

        available = ", ".join(
            sorted(
                config.providers
            )
        )

        raise LLMConfigurationError(
            (
                f"Unknown LLM provider "
                f"'{selected_name}'. "
                f"Available providers: "
                f"{available}"
            )
        )

    if not provider_config.enabled:
        raise LLMConfigurationError(
            (
                f"LLM provider "
                f"'{selected_name}' "
                f"is disabled."
            )
        )

    provider_type = (
        provider_config.type
    )

    if (
        provider_type
        == ProviderType.OPENAI
    ):
        return OpenAIProvider(
            provider_alias=(
                selected_name
            ),
            config=provider_config,
        )

    if (
        provider_type
        == ProviderType.ANTHROPIC
    ):
        return AnthropicProvider(
            provider_alias=(
                selected_name
            ),
            config=provider_config,
        )

    if (
        provider_type
        == ProviderType.GEMINI
    ):
        return GeminiProvider(
            provider_alias=(
                selected_name
            ),
            config=provider_config,
        )

    if (
        provider_type
        == ProviderType.GROK
    ):
        return GrokProvider(
            provider_alias=(
                selected_name
            ),
            config=provider_config,
        )

    if (
        provider_type
        == ProviderType.OLLAMA
    ):
        return OllamaProvider(
            provider_alias=(
                selected_name
            ),
            config=provider_config,
        )

    if (
        provider_type
        == (
            ProviderType
            .OPENAI_COMPATIBLE
        )
    ):
        return (
            OpenAICompatibleProvider(
                provider_alias=(
                    selected_name
                ),
                config=(
                    provider_config
                ),
            )
        )

    if (
        provider_type
        == ProviderType.MOCK
    ):
        return MockActionProvider(
            provider_alias=(
                selected_name
            ),
            model_name=(
                provider_config.model
            ),
        )

    raise LLMConfigurationError(
        (
            "Unsupported provider "
            f"type: {provider_type}"
        )
    )