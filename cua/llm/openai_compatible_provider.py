from __future__ import annotations

import os

from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI

from cua.models import (
    AgentAction,
    Observation,
)
from cua.llm.normalization import (
    parse_text_proposal,
)
from cua.llm.base import (
    ActionProvider,
    LLMConfigurationError,
    LLMProviderError,
    proposal_to_agent_action,
)

from cua.llm.config import (
    ProviderConfig,
)

from cua.llm.prompts import (
    DISCOVERY_INSTRUCTIONS,
    build_discovery_input,
)

from cua.llm.schemas import (
    LLMActionProposal,
)


class OpenAICompatibleProvider(
    ActionProvider
):
    """
    Provider for self-hosted or third-party servers
    implementing an OpenAI-compatible chat API.

    Example:
        vLLM

    The server must support JSON-schema structured output.
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

        if not config.base_url:
            raise LLMConfigurationError(
                (
                    "openai_compatible provider "
                    "requires base_url."
                )
            )

        self.base_url = config.base_url

        if client is None:

            if config.api_key_env:

                api_key = os.getenv(
                    config.api_key_env
                )

                if not api_key:
                    raise LLMConfigurationError(
                        (
                            "Environment variable "
                            f"'{config.api_key_env}' "
                            "is not configured."
                        )
                    )

            else:
                # Many local OpenAI-compatible servers
                # require some value even if auth is ignored.
                api_key = "local"

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=config.base_url,
                timeout=config.timeout_seconds,
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

        input_text = build_discovery_input(
            goal=goal,
            observation=observation,
            previous_actions=(
                previous_actions
            ),
            step_index=step_index,
            max_steps=max_steps,
        )

        response_format = {
            "type": "json_schema",

            "json_schema": {
                "name": (
                    "llm_action_proposal"
                ),

                "strict": True,

                "schema": (
                    LLMActionProposal
                    .model_json_schema()
                ),
            },
        }

        try:
            completion = (
                await self
                .client
                .chat
                .completions
                .create(
                    model=self.model_name,

                    messages=[
                        {
                            "role": "system",
                            "content": (
                                DISCOVERY_INSTRUCTIONS
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                input_text
                            ),
                        },
                    ],

                    response_format=(
                        response_format
                    ),

                    max_tokens=(
                        self.config
                        .max_output_tokens
                    ),
                )
            )

        except Exception as exc:
            raise LLMProviderError(
                (
                    "OpenAI-compatible "
                    "request failed: "
                    f"{exc}"
                )
            ) from exc

        self.last_request_id = getattr(
            completion,
            "id",
            None,
        )

        content = (
            completion
            .choices[0]
            .message
            .content
        )

        if not content:
            raise LLMProviderError(
                (
                    "OpenAI-compatible "
                    "response contained "
                    "no content."
                )
            )

        proposal = (
    parse_text_proposal(
        content
    )
)

        return proposal_to_agent_action(
            proposal
        )