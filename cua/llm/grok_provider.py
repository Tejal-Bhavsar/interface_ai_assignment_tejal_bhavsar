from __future__ import annotations

from collections.abc import (
    Sequence,
)
from typing import Any

from openai import AsyncOpenAI

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


DEFAULT_XAI_BASE_URL = (
    "https://api.x.ai/v1"
)


class GrokProvider(
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

        self.base_url = (
            config.base_url
            or DEFAULT_XAI_BASE_URL
        )

        if client is None:
            api_key = require_api_key(
                config.api_key_env
            )

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.base_url,
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

        try:
            completion = (
                await self
                .client
                .beta
                .chat
                .completions
                .parse(
                    model=(
                        self.model_name
                    ),

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
                        LLMActionProposal
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
                    "xAI/Grok request "
                    f"failed: {exc}"
                )
            ) from exc

        self.last_request_id = (
            getattr(
                completion,
                "id",
                None,
            )
        )

        message = (
            completion
            .choices[0]
            .message
        )

        refusal = getattr(
            message,
            "refusal",
            None,
        )

        if refusal:
            raise LLMRefusalError(
                str(refusal)
            )

        proposal = getattr(
            message,
            "parsed",
            None,
        )

        if proposal is None:
            raise LLMProviderError(
                (
                    "Grok response "
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