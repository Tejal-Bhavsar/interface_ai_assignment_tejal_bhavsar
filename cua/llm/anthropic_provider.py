from __future__ import annotations

import asyncio

from collections.abc import (
    Sequence,
)
from typing import Any

from anthropic import Anthropic

from cua.models import (
    AgentAction,
    Observation,
)

from cua.llm.base import (
    ActionProvider,
    LLMProviderError,
    LLMRefusalError,
    proposal_to_agent_action,
    require_api_key,
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


class AnthropicProvider(
    ActionProvider
):

    def __init__(
        self,
        *,
        provider_alias: str,
        config: ProviderConfig,
        client: Any | None = None,
    ):
        super().__init__(
            provider_alias=(
                provider_alias
            ),
            model_name=config.model,
        )

        self.config = config

        if client is None:
            api_key = require_api_key(
                config.api_key_env
            )

            client = Anthropic(
                api_key=api_key,
                timeout=(
                    config
                    .timeout_seconds
                ),
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
                observation=(
                    observation
                ),
                previous_actions=(
                    previous_actions
                ),
                step_index=step_index,
                max_steps=max_steps,
            )
        )

        def call_api():
            return (
                self.client
                .messages
                .parse(
                    model=(
                        self.model_name
                    ),

                    max_tokens=(
                        self.config
                        .max_output_tokens
                    ),

                    system=(
                        DISCOVERY_INSTRUCTIONS
                    ),

                    messages=[
                        {
                            "role": "user",
                            "content": (
                                input_text
                            ),
                        }
                    ],

                    output_format=(
                        LLMActionProposal
                    ),
                )
            )

        try:
            response = (
                await asyncio.to_thread(
                    call_api
                )
            )

        except Exception as exc:
            raise LLMProviderError(
                (
                    "Anthropic request "
                    f"failed: {exc}"
                )
            ) from exc

        self.last_request_id = (
            getattr(
                response,
                "id",
                None,
            )
        )

        if (
            getattr(
                response,
                "stop_reason",
                None,
            )
            == "refusal"
        ):
            raise LLMRefusalError(
                (
                    "Anthropic model "
                    "refused the request."
                )
            )

        proposal = getattr(
            response,
            "parsed_output",
            None,
        )

        if proposal is None:
            raise LLMProviderError(
                (
                    "Anthropic response "
                    "contained no "
                    "parsed action."
                )
            )

        if not isinstance(
            proposal,
            LLMActionProposal,
        ):
            proposal = (
                LLMActionProposal
                .model_validate(
                    proposal
                )
            )

        return proposal_to_agent_action(
            proposal
        )