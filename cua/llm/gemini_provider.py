from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types

from cua.models import (
    AgentAction,
    Observation,
)

from cua.llm.base import (
    ActionProvider,
    LLMProviderError,
    proposal_to_agent_action,
    require_api_key,
)

from cua.llm.config import (
    ProviderConfig,
)

from cua.llm.normalization import (
    parse_text_proposal,
)

from cua.llm.prompts import (
    DISCOVERY_INSTRUCTIONS,
    build_discovery_input,
)

from cua.llm.schemas import (
    LLMActionProposal,
)


class GeminiProvider(
    ActionProvider
):
    """
    Gemini implementation of ActionProvider.

    Uses Gemini generateContent with native JSON Schema
    structured output.

    The implementation is intentionally model-version
    independent. The configured Gemini model may change,
    but the provider contract remains the same.
    """

    def __init__(
        self,
        *,
        provider_alias: str,
        config: ProviderConfig,
        client: Any | None = None,
    ):
        super().__init__(
            provider_alias=provider_alias,
            model_name=config.model,
        )

        self.config = config

        if client is None:
            api_key = require_api_key(
                config.api_key_env
            )

            client = genai.Client(
                api_key=api_key
            )

        self.client = client

    async def decide(
        self,
        *,
        goal: str,
        observation: Observation,
        previous_actions: Sequence[
            AgentAction
        ] = (),
        step_index: int = 1,
        max_steps: int = 12,
    ) -> AgentAction:

        input_text = (
            build_discovery_input(
                goal=goal,
                observation=observation,
                previous_actions=(
                    previous_actions
                ),
                step_index=step_index,
                max_steps=max_steps,
            )
        )

        config = (
            types.GenerateContentConfig(
                system_instruction=(
                    DISCOVERY_INSTRUCTIONS
                ),

                response_mime_type=(
                    "application/json"
                ),

                # IMPORTANT:
                #
                # We pass raw JSON Schema rather than the
                # older response_schema=PydanticModel path.
                #
                # This avoids provider-side conversion of
                # our strict Pydantic schema into Google's
                # older Schema protobuf representation.
                response_json_schema=(
                    LLMActionProposal
                    .model_json_schema()
                ),

                max_output_tokens=(
                    self.config
                    .max_output_tokens
                ),

                temperature=0,

                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                ),
            )
        )

        try:
            response = (
                await self
                .client
                .aio
                .models
                .generate_content(
                    model=self.model_name,
                    contents=input_text,
                    config=config,
                )
            )

        except Exception as exc:
            raise LLMProviderError(
                (
                    "Gemini request "
                    f"failed: {exc}"
                )
            ) from exc

        self.last_request_id = getattr(
            response,
            "response_id",
            None,
        )

        output_text = getattr(
            response,
            "text",
            None,
        )

        if not output_text:
            raise LLMProviderError(
                (
                    "Gemini response "
                    "contained no structured "
                    "output text."
                )
            )

        # Defensive common parsing boundary.
        #
        # Cosmetic differences such as an outer Markdown
        # fence may be normalized, but structural schema
        # violations still fail closed.
        proposal = (
            parse_text_proposal(
                output_text
            )
        )

        return proposal_to_agent_action(
            proposal
        )